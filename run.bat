@echo off
IF NOT EXIST venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python init_db.py
echo Starting app...
python app.py