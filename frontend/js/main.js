document.addEventListener('DOMContentLoaded', function() {
    // Tab switching functionality
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', function() {
            const target = this.dataset.target;
            
            // Update active tab button
            tabButtons.forEach(btn => btn.classList.remove('active'));
            this.classList.add('active');
            
            // Show corresponding tab content
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(`${target}-content`).classList.add('active');
        });
    });
    
    // Setup upload areas for both Aadhaar and PAN
    setupUploadArea('aadhaar');
    setupUploadArea('pan');
    
    // Setup extract buttons
    setupExtractButton('aadhaar', '/extract_aadhaar');
    setupExtractButton('pan', '/extract_pan');
    
    // Setup action buttons
    setupActionButtons('aadhaar');
    setupActionButtons('pan');
});

// Function to handle file upload areas
function setupUploadArea(type) {
    const uploadArea = document.getElementById(`${type}-upload`);
    const fileInput = document.getElementById(`${type}-file`);
    const filenameElement = document.getElementById(`${type}-filename`);
    const extractButton = document.getElementById(`${type}-extract-btn`);
    
    // Click on upload area to trigger file input
    uploadArea.addEventListener('click', () => {
        fileInput.click();
    });
    
    // Handle file selection
    fileInput.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
            if (file.type === 'application/pdf') {
                filenameElement.textContent = file.name;
                extractButton.disabled = false;
            } else {
                showNotification('Please select a PDF file', 'error');
                fileInput.value = '';
                filenameElement.textContent = 'No file selected';
                extractButton.disabled = true;
            }
        }
    });
    
    // Handle drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        uploadArea.addEventListener(eventName, () => {
            uploadArea.classList.add('dragover');
        });
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        uploadArea.addEventListener(eventName, () => {
            uploadArea.classList.remove('dragover');
        });
    });
    
    uploadArea.addEventListener('drop', (e) => {
        const file = e.dataTransfer.files[0];
        if (file) {
            if (file.type === 'application/pdf') {
                fileInput.files = e.dataTransfer.files;
                filenameElement.textContent = file.name;
                extractButton.disabled = false;
            } else {
                showNotification('Please select a PDF file', 'error');
            }
        }
    });
}

// Function to handle extract buttons
function setupExtractButton(type, endpoint) {
    const extractButton = document.getElementById(`${type}-extract-btn`);
    const fileInput = document.getElementById(`${type}-file`);
    const loader = document.getElementById(`${type}-loader`);
    const uploadSection = document.querySelector(`#${type}-content .upload-section`);
    const results = document.getElementById(`${type}-results`);
    
    extractButton.addEventListener('click', async () => {
        if (!fileInput.files[0]) {
            showNotification('Please select a file first', 'error');
            return;
        }
        
        // Show loader
        loader.style.display = 'flex';
        
        // Create form data
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        
        try {
            // Send request to API
            const response = await fetch(endpoint, {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                // Hide loader
                loader.style.display = 'none';
                
                // Hide upload section
                uploadSection.style.display = 'none';
                
                // Display results
                displayResults(type, data.data);
                results.style.display = 'block';
                
                // Store data for later use
                window[`${type}Data`] = data.data;
                
                showNotification('Information extracted successfully', 'success');
            } else {
                throw new Error(data.message || data.error || 'Failed to extract information');
            }
        } catch (error) {
            console.error('Error:', error);
            loader.style.display = 'none';
            showNotification(error.message || 'An error occurred', 'error');
        }
    });
}

// Function to display extracted results
function displayResults(type, data) {
    if (type === 'aadhaar') {
        document.getElementById('aadhaar-name').textContent = data.name || '-';
        document.getElementById('aadhaar-dob').textContent = data.dob || '-';
        document.getElementById('aadhaar-gender').textContent = data.gender || '-';
        document.getElementById('aadhaar-number').textContent = data.aadhaar_number || '-';
        document.getElementById('aadhaar-address').textContent = data.address || '-';
    } else if (type === 'pan') {
        document.getElementById('pan-name').textContent = data.name || '-';
        document.getElementById('pan-father-name').textContent = data.father_name || '-';
        document.getElementById('pan-dob').textContent = data.dob || '-';
        document.getElementById('pan-number').textContent = data.pan_number || '-';
    }
}

// Function to setup action buttons (copy, download, reset)
function setupActionButtons(type) {
    const copyBtn = document.getElementById(`${type}-copy-btn`);
    const downloadBtn = document.getElementById(`${type}-download-btn`);
    const resetBtn = document.getElementById(`${type}-reset-btn`);
    
    // Copy to clipboard
    copyBtn.addEventListener('click', () => {
        const data = window[`${type}Data`];
        if (data) {
            const textToCopy = JSON.stringify(data, null, 2);
            navigator.clipboard.writeText(textToCopy)
                .then(() => {
                    showNotification('Copied to clipboard!', 'success');
                })
                .catch(() => {
                    showNotification('Failed to copy', 'error');
                });
        }
    });
    
    // Download as JSON
    downloadBtn.addEventListener('click', () => {
        const data = window[`${type}Data`];
        if (data) {
            const jsonString = JSON.stringify(data, null, 2);
            const blob = new Blob([jsonString], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `${type}_card_details.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            showNotification('Downloaded successfully', 'success');
        }
    });
    
    // Reset
    resetBtn.addEventListener('click', () => {
        resetForm(type);
    });
}

// Function to reset the form
function resetForm(type) {
    // Reset file input
    const fileInput = document.getElementById(`${type}-file`);
    fileInput.value = '';
    
    // Reset filename text
    const filenameElement = document.getElementById(`${type}-filename`);
    filenameElement.textContent = 'No file selected';
    
    // Disable extract button
    const extractButton = document.getElementById(`${type}-extract-btn`);
    extractButton.disabled = true;
    
    // Hide results
    const results = document.getElementById(`${type}-results`);
    results.style.display = 'none';
    
    // Show upload section
    const uploadSection = document.querySelector(`#${type}-content .upload-section`);
    uploadSection.style.display = 'block';
    
    // Clear stored data
    window[`${type}Data`] = null;
}

// Function to show notifications
function showNotification(message, type = 'info') {
    const notification = document.getElementById('notification');
    const notificationText = document.getElementById('notification-text');
    
    // Set message
    notificationText.textContent = message;
    
    // Set color based on type
    if (type === 'error') {
        notification.style.backgroundColor = '#f72585';
    } else if (type === 'success') {
        notification.style.backgroundColor = '#4cc9f0';
    } else {
        notification.style.backgroundColor = '#333';
    }
    
    // Show notification
    notification.classList.add('show');
    
    // Hide after 3 seconds
    setTimeout(() => {
        notification.classList.remove('show');
    }, 3000);
}