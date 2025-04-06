from flask import Flask, request, jsonify
import pytesseract
from pdf2image import convert_from_bytes
import re
import os
import platform
from werkzeug.utils import secure_filename
from datetime import datetime

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
            # Use pytesseract with English language option
            text = pytesseract.image_to_string(image, lang='eng')
            all_text += text + "\n"
            
        return all_text
    except Exception as e:
        return str(e)


def extract_pan_details(text):
    """Parse the extracted text to get PAN card details"""
    details = {
        "name": None,
        "father_name": None,
        "dob": None,
        "pan_number": None
    }
    
    # Preserve the original text for debugging
    original_text = text
    
    # Clean the text while preserving line breaks for better pattern matching
    cleaned_text = re.sub(r'[^\w\s/\n]', ' ', text)
    lines = cleaned_text.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]
    
    # 1. Extract PAN number (10 characters, 5 letters, 4 numbers, 1 letter)
    pan_pattern = r'[A-Z]{5}[0-9]{4}[A-Z]'
    pan_matches = re.findall(pan_pattern, cleaned_text)
    if pan_matches:
        details["pan_number"] = pan_matches[0].upper()
    
    # 2. Extract name - identify line with name marker
    name_line_index = -1
    for i, line in enumerate(non_empty_lines):
        if re.search(r'(?:aT\s*/\s*Name|Name|\bNAME\b|~)', line, re.IGNORECASE):
            name_line_index = i
            break
    
    # If we found a line with name marker, the next line is likely the name
    if name_line_index >= 0 and name_line_index + 1 < len(non_empty_lines):
        name_candidate = non_empty_lines[name_line_index + 1]
        # Clean the name
        name_candidate = re.sub(r'(?i)(name|card|permanent|account|number)', '', name_candidate)
        # Remove any digits from the name
        name_candidate = re.sub(r'\d+', '', name_candidate)
        name_candidate = re.sub(r'\s+', ' ', name_candidate).strip()
        if name_candidate and not re.match(pan_pattern, name_candidate):
            details["name"] = name_candidate.title()
    
    # If name not found, try alternative patterns
    if not details["name"]:
        name_patterns = [
            r'(?:Name|Permanent Account Number Card|~|aT\s*/\s*Name)\s*([A-Z][A-Z\s]+)(?=\n|$)',
            r'(?:\n|^)([A-Z][A-Z\s]+)\n(?:Father|Mother|Date)',
            r'(?:Name\s*:\s*)([A-Z][A-Z\s]+)'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, cleaned_text, re.MULTILINE)
            if name_match:
                name = name_match.group(1).strip()
                # Clean the name and remove digits
                name = re.sub(r'(?i)(name|card|permanent|account|number)', '', name)
                name = re.sub(r'\d+', '', name)
                name = re.sub(r'\s+', ' ', name).strip()
                if name and len(name.split()) >= 2:  # At least first and last name
                    details["name"] = name.title()
                    break
    
    # 3. Extract father's name - first identify if there's a marker in the text
    father_marker_exists = re.search(r'(?:Father\'?s?\s*Name|S/O|D/O)', cleaned_text, re.IGNORECASE)
    
    if father_marker_exists:
        # If a marker exists, use patterns specific to labeled father's names
        father_patterns = [
            r'(?:Father\'?s?\s*Name\s*:?\s*)([A-Z][A-Z\s]+)',
            r'(?:S/O|D/O)\s*([A-Z][A-Z\s]+)',
        ]
        
        for pattern in father_patterns:
            father_match = re.search(pattern, cleaned_text, re.MULTILINE | re.IGNORECASE)
            if father_match:
                father_name = father_match.group(1).strip()
                # Clean father's name and remove digits
                father_name = re.sub(r'(?i)(father|name|s/o|d/o)', '', father_name)
                father_name = re.sub(r'\d+', '', father_name)
                father_name = re.sub(r'\s+', ' ', father_name).strip()
                if father_name and len(father_name.split()) >= 2:
                    details["father_name"] = father_name.title()
                    break
    else:
        # If no father marker exists, look for a standalone line that isn't the name or PAN
        # This is tricky - try to identify the line based on position and context
        
        # Typically names are in consecutive lines with the name coming first
        name_index = -1
        for i, line in enumerate(non_empty_lines):
            if details["name"] and details["name"].upper() in line.upper():
                name_index = i
                break
        
        # If we found the name line, the line following it might be the father's name
        if name_index >= 0 and name_index + 1 < len(non_empty_lines):
            father_candidate = non_empty_lines[name_index + 1]
            # Remove any digits that might be part of dates
            father_candidate = re.sub(r'\d+', '', father_candidate).strip()
            # Check if this line doesn't contain any markers, PAN number
            if (not re.search(r'(?:Name|PAN|Number|Card|Date|DOB)', father_candidate, re.IGNORECASE) and
                not re.search(pan_pattern, father_candidate)):
                
                # Make sure it looks like a name (2+ words, all caps)
                if len(father_candidate.split()) >= 2 and father_candidate.isupper():
                    details["father_name"] = father_candidate.title()
    
    # 4. If we still don't have a father name, try to extract from lines with date patterns
    if not details["father_name"]:
        date_lines = []
        for i, line in enumerate(non_empty_lines):
            if re.search(r'\d{8}|\d{2}[/-]\d{2}[/-]\d{4}', line):
                date_lines.append((i, line))
        
        for i, line in date_lines:
            # Remove the date part
            line_without_date = re.sub(r'\d{8}|\d{2}[/-]\d{2}[/-]\d{4}', '', line).strip()
            # Check if what remains looks like a name
            if len(line_without_date.split()) >= 2 and line_without_date.isupper():
                # Make sure it's different from the card holder's name
                if details["name"] and line_without_date.upper() != details["name"].upper():
                    details["father_name"] = line_without_date.title()
                    break
    
    # 5. Extract Date of Birth - handle multiple dates and formats
    date_patterns = [
        r'(?:Date\s*of\s*Birth|DOB|Birth)\s*:\s*(\d{2}[/-]\d{2}[/-]\d{4})',
        r'(?:Year\s*of\s*Birth|YOB)\s*:\s*(\d{4})',
        r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b',
        r'\b(\d{8})\b(?!.*[A-Z]{5}\d{4}[A-Z])'  # 8-digit date not part of PAN
    ]
    
    all_dates = []
    for pattern in date_patterns:
        date_matches = re.findall(pattern, cleaned_text)
        for date in date_matches:
            # Format 8-digit dates (ddmmyyyy) to dd/mm/yyyy
            if len(date) == 8 and date.isdigit():
                formatted_date = f"{date[:2]}/{date[2:4]}/{date[4:8]}"
                all_dates.append(formatted_date)
            else:
                all_dates.append(date)
    
    # Filter out dates that might be part of other fields
    valid_dates = []
    for date in all_dates:
        # Skip if it's part of PAN number
        if details["pan_number"] and date.replace('/', '') in details["pan_number"]:
            continue
        
        # Try to validate and parse date format
        try:
            if '/' in date:
                day, month, year = map(int, date.split('/'))
            elif '-' in date:
                day, month, year = map(int, date.split('-'))
            elif len(date) == 8:  # Format like 21052023
                day, month, year = int(date[:2]), int(date[2:4]), int(date[4:8])
            else:
                continue
                
            # Basic date validation
            if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= datetime.now().year:
                valid_dates.append(f"{day:02d}/{month:02d}/{year}")
        except:
            # If parsing fails, keep the original format
            valid_dates.append(date)
    
    if valid_dates:
        details["dob"] = valid_dates[0]
    
    # Final validation: Ensure name and father_name have at most 3 words
    if details["name"]:
        name_words = details["name"].split()
        if len(name_words) > 3:
            details["name"] = " ".join(name_words[:3])
    
    if details["father_name"]:
        father_words = details["father_name"].split()
        if len(father_words) > 3:
            details["father_name"] = " ".join(father_words[:3])
    
    return details
        
@app.route('/extract_pan', methods=['POST'])
def extract_pan():
    """API endpoint to extract PAN details from uploaded PDF"""
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
            
            # Parse text to get PAN details
            pan_details = extract_pan_details(extracted_text)
            
            # Post-process: Enhance confidence by checking critical fields
            if not pan_details["pan_number"]:
                return jsonify({
                    "status": "error",
                    "message": "Could not identify PAN number - please check if the document is a valid PAN card"
                }), 400
            
            # Return the extracted details as JSON
            return jsonify({
                "status": "success",
                "data": pan_details,
                "raw_text": extracted_text  # Include raw text for debugging purposes
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Only PDF files are allowed"}), 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)