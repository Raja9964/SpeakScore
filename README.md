Case Study Scorer - Project Package

This package contains a lightweight scorer that parses the uploaded rubric Excel, scores a self-introduction transcript, and returns per-criterion feedback + an overall score.

Files included
- `Case study for interns.xlsx` (original rubric Excel)
- `Nirmaan AI intern Case study instructions.pdf`
- `Sample text for case study.txt` (the sample transcript)
- `case_study_scoring_refined.json` (scoring output from the sample run)
- `parsed_rubric.json` (rubric JSON extracted by the parser)
- `case_study_scoring_output.json` (earlier run output)
- `app.py` (Flask app)
- `scorer.py` (scoring logic)
- `templates/index.html` (simple UI)
- `requirements.txt` (python deps)

Notes
- The scorer uses TF-IDF for semantic similarity; for improved quality you can use sentence-transformers.
- The rubric parsing is heuristic-based for the provided Excel layout. If you change the Excel layout the parser may need tweak.
