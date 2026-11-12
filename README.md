
# INGRES Chatbot

AI-driven conversational chatbot for querying India's groundwater assessment data (INGRES).

## Features
- Groundwater data processing
- Block-level geographical data handling
- SQLite database generation
- Foundation for AI-driven natural language queries

## Technologies Used
- Python
- GeoPandas
- Pandas
- NumPy
- Shapely
- SQLite

## Setup

1. Clone this repository.
2. Create a virtual environment:

   python -m venv .venv

3. Activate the environment:

   .venv\Scripts\activate

4. Install dependencies:

   pip install -r requirements.txt

5. Download AU2020.geojson from the shared Google Drive link.

6. Place AU2020.geojson inside the data folder.

7. Generate the database:

   python build_db.py

## Project Structure

ingres-chatbot/
├── data/
├── build_db.py
├── requirements.txt
├── README.md
└── .gitignore
