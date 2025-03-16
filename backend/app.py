from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import os
import datetime

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing for frontend access

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple endpoint to check if the API is running"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """
    Endpoint to handle CSV file upload
    Reads the CSV file and returns column headers
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    if file and file.filename.endswith('.csv'):
        try:
            # Read the CSV file
            df = pd.read_csv(file)

            # Get column names (headers)
            columns = df.columns.tolist()

            # Return the column names and basic stats
            return jsonify({
                "success": True,
                "columns": columns,
                "rowCount": len(df),
                "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Not a CSV file"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)