from flask import Flask, request, jsonify, render_template
import os
from scorer import score_transcript

app = Flask(__name__, static_folder='static', template_folder='templates')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/score', methods=['POST'])
def score():
    data = request.json
    text = data.get('transcript','')
    excel_path = os.environ.get("RUBRIC_EXCEL_PATH", "Case study for interns.xlsx")
    out = score_transcript(text, excel_path=excel_path)
    return jsonify(out)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
