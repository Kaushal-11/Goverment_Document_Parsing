from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import re
from werkzeug.utils import secure_filename
from aadhar import extract_text_from_pdf as extract_aadhaar_text, extract_aadhaar_details
from pan import extract_text_from_pdf as extract_pan_text, extract_pan_details

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return app.send_static_file('index.html')

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
            extracted_text = extract_aadhaar_text(file)
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
            extracted_text = extract_pan_text(file)
            
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
    app.run(debug=True)