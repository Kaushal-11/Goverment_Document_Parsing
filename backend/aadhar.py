from flask import Flask, request, jsonify
import pytesseract
from pdf2image import convert_from_bytes
import re
import os
import platform
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure Tesseract path for Windows
if platform.system() == 'Windows':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_file):
    """Convert PDF to images and extract text using OCR"""
    try:
        # Convert PDF to images
        images = convert_from_bytes(pdf_file.read())
        
        # Extract text from each page
        all_text = ""
        for image in images:
            # Use pytesseract with English language option to focus on English text
            text = pytesseract.image_to_string(image, lang='eng+guj')
            all_text += text + "\n"
            
        return all_text
    except Exception as e:
        return str(e)

def extract_aadhaar_details(text):
    """Parse the extracted text to get Aadhaar card details without relying on field headers"""
    # Initialize empty result dictionary
    details = {
        "name": None,
        "dob": None,
        "gender": None,
        "aadhaar_number": None,
        "address": None
    }
    
    # Extract Aadhaar number (12 digits with or without spaces)
    aadhaar_pattern = r'\b\d{4}\s?\d{4}\s?\d{4}\b'
    aadhaar_matches = re.findall(aadhaar_pattern, text)
    if aadhaar_matches:
        # Format to standard format with spaces
        raw_number = re.sub(r'\s', '', aadhaar_matches[0])
        details["aadhaar_number"] = f"{raw_number[:4]} {raw_number[4:8]} {raw_number[8:12]}"
    
    # Extract DOB (multiple common formats)
    dob_patterns = [
        r'(?i)(?:DOB|Date of Birth|Birth)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})',  # With header
        r'(?i)(?:DOB|Date of Birth|Birth)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})'  # With header
    ]
    
    dob_match = None
    for pattern in dob_patterns:
        dob_matches = re.search(pattern, text)
        if dob_matches:
            dob_match = dob_matches.group(1)
            break
    
    # If no match found with header, look for date format
    if not dob_match:
        date_pattern = r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b'
        date_matches = re.findall(date_pattern, text)
        if date_matches:
            # Filter out Issue Date and Print Date
            for date in date_matches:
                line_with_date = next((line for line in text.split('\n') if date in line), '')
                if not re.search(r'(?:Issue|Print)\s+Date', line_with_date, re.IGNORECASE):
                    dob_match = date
                    break
    
    if dob_match:
        details["dob"] = dob_match
    
    # Extract gender - look for standalone MALE or FEMALE near the word Male/Female
    gender_patterns = [
        r'(?i)(?:Gender|Sex)[:\s]+(Male|Female)',  # With header
        r'(?i)[:/\s]*(Male|Female)[:/\s]*',        # Standalone gender
        r'(?i)(\bMale\b|\bFemale\b)'               # Just the word
    ]
    
    for pattern in gender_patterns:
        gender_matches = re.search(pattern, text)
        if gender_matches:
            details["gender"] = gender_matches.group(1).upper()
            break
    
    exclude_words = ["male", "female", "address", "date", "issue", "print", "year", "birth", 
                     "dob", "art", "uid", "uidai", "aadhaar", "aadhar", "number", "mobile", 
                     "phone", "wot", "verify", "front", "back", "govt", "government"]
    
    name_patterns = [
        r'([A-Z][A-Za-z]+)\s+([A-Z][A-Za-z]+)[^\n]*\n([A-Z][A-Za-z]+)',
        r'([A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+)\s*\n\s*([A-Z][A-Za-z]+\s+[A-Za-z]+)',
        r'([A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+)',
        r"(?:Issue Date:.*?\n\n)(.*?)(?:\n)",
        r"^([A-Za-z\s]+)(?=\nDate of Birth)"
    ]

    name_parts = []
    name_matches = []
    
    # First pass: collect all potential name parts
    for i, line in enumerate(text.split('\n')):
        # Clean the line - keep only valid alphabetic characters and spaces
        clean_line = re.sub(r'[^A-Za-z\s]', '', line)
        words = clean_line.split()
        
        # Check if line contains valid name parts (all-caps words of reasonable length)
        valid_name_words = [
            word for word in words 
            if word.isupper() and 3 <= len(word) <= 15
            and word.lower() not in exclude_words
        ]
        if valid_name_words:
            name_parts.extend(valid_name_words)
    
    # If we found potential name parts, combine them (max 3 words)
    if len(name_parts) >= 2:
        # Take only the first 3 name parts
        name_parts = name_parts[:3]
        combined_name = " ".join(name_parts)
        name_matches.append(combined_name)
    
    # Second pass: use your existing regex patterns
    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            if isinstance(match, tuple):
                # For multi-part matches
                parts = [part.strip() for part in match if part.strip()]
                # Limit to first 3 parts
                parts = parts[:3]
                full_name = " ".join(parts)
            else:
                # Single match
                full_name = match.strip()
                
            # Clean the name - remove any non-alphabetic characters
            full_name = re.sub(r'[^A-Za-z\s]', '', full_name)
            
            # Skip if it contains common non-name words
            if not any(word.lower() in full_name.lower() for word in exclude_words):
                # Limit to 3 words maximum
                name_words = full_name.split()
                if len(name_words) > 3:
                    full_name = " ".join(name_words[:3])
                name_matches.append(full_name)
    
    # Select the longest valid name (likely the full name)
    if name_matches:
        # Clean up each match
        cleaned_matches = []
        for name in name_matches:
            # Standardize spaces
            clean_name = re.sub(r'\s+', ' ', name).strip()
            # Remove any non-name strings that might have slipped through
            words = clean_name.split()
            valid_words = [
                word for word in words 
                if len(word) >= 2 and re.match(r'^[A-Za-z]+$', word)
                and word.lower() not in exclude_words
            ]
            
            # Ensure maximum 3 words
            valid_words = valid_words[:3]
            
            if len(valid_words) >= 2:  # At least first and last name
                cleaned_matches.append(" ".join(valid_words))
        
        # Sort by length and take the longest one
        if cleaned_matches:
            cleaned_matches.sort(key=len, reverse=True)
            details["name"] = cleaned_matches[0].title()

    # Extract address - look for "Address:" or typical address format with street, city, state, PIN
    address_patterns = [
        r'(?i)Address\s*:(.+?)(?=\n\n|\n\w|\Z)',  # Address with header until next section
        r'(?i)Address:([^,]+,[^,]+,[^,]+,.*?\d{6})',  # Common Indian address format with PIN
        r'(?i)([^,]+,[^,]+,[^,]+,.*?\d{6})'  # Just the address format without header
    ]
    
    for pattern in address_patterns:
        address_matches = re.search(pattern, text, re.DOTALL)
        if address_matches:
            # Clean up the address
            address = address_matches.group(1).strip()
            # Remove any excessive whitespace
            address = re.sub(r'\s+', ' ', address).strip()
            
            # Only accept if it looks like an address (has commas and a PIN code)
            if "," in address and re.search(r'\d{6}', address):
                details["address"] = address
                break
    
    return details

@app.route('/extract_aadhaar', methods=['POST'])
def extract_aadhaar():
    """API endpoint to extract Aadhaar details from uploaded PDF"""
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    
    # If user does not select file, browser also submit empty part without filename
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        try:
            # Extract text from PDF
            extracted_text = extract_text_from_pdf(file)
            
            # Enhanced extraction specifically for addresses
            # Look specifically for a line containing "Address:" followed by content
            address_line_match = re.search(r'(?i)Address:(.*?)(?=\n\n|\n[A-Z]|\Z)', extracted_text, re.DOTALL)
            address = None
            if address_line_match:
                address = address_line_match.group(1).strip()
                address = re.sub(r'\s+', ' ', address)
            
            # Parse text to get Aadhaar details
            aadhaar_details = extract_aadhaar_details(extracted_text)
            
            # If we found address in the special case but not in the regular extraction
            if address and not aadhaar_details["address"]:
                aadhaar_details["address"] = address
            
            # For the specific format seen in the example, try to extract name by finding a line
            # that looks like a name before DOB and not containing "Issue Date"
            if not aadhaar_details["name"] or "issue" in aadhaar_details["name"].lower():
                lines = extracted_text.split('\n')
                for i, line in enumerate(lines):
                    if "DOB" in line or "Date of Birth" in line:
                        # Check 1-3 lines before this one for potential name
                        for j in range(1, 4):
                            if i-j >= 0:
                                potential_name = lines[i-j].strip()
                                # Check if it looks like a name (no digits, not too short, not common words)
                                if (len(potential_name) > 5 and 
                                    not re.search(r'\d', potential_name) and
                                    not any(word.lower() in potential_name.lower() for word in 
                                           ["issue", "date", "print", "address", "male", "female"])):
                                    aadhaar_details["name"] = potential_name.title()
                                    break
                        break
            
            # Post-process: Enhance confidence by checking critical fields
            if not aadhaar_details["aadhaar_number"]:
                return jsonify({
                    "status": "error",
                    "message": "Could not identify Aadhaar number - please check if the document is a valid Aadhaar card"
                }), 400
            
            # Return the extracted details as JSON
            return jsonify({
                "status": "success",
                "data": aadhaar_details,
                "raw_text": extracted_text  # Include raw text for debugging purposes
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Only PDF files are allowed"}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)