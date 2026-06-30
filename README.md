# Biogas User Survey Dashboard

## Overview
This dashboard visualizes the Indonesia Domestic Biogas Program (IDBP) survey data collected across multiple provinces in Indonesia. The application processes and presents key metrics from the Biogas User Survey (BUS), highlighting impacts on health, socio-economic conditions, technical performance, user satisfaction, gender impacts, agriculture systems, and environmental benefits of biogas digesters.

The dashboard serves as an analytical tool to measure user satisfaction, assess technical performance of biogas digesters, and monitor carbon emission reductions in line with Gold Standard certification requirements.

## What's in this Repository
- **main_app.py**: The main Streamlit application that serves as the entry point and handles the user interface
- **chart_gen.py**: A utility class for generating and customizing visualizations within the dashboard
- **requirements.txt**: List of Python package dependencies required to run the application
- **survey_data-G_3.csv**: Sample dataset containing the biogas user survey results

## Getting Started

### Prerequisites
- Python 3.11 is recommended
- pip (Python package installer)

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install required dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Streamlit application**
   ```bash
   streamlit run main_app.py
   ```

4. **Access the dashboard**
   Open your web browser and navigate to the URL displayed in your terminal (typically http://localhost:8501)

### Usage
The dashboard presents various visualizations and metrics derived from the Biogas User Survey data across multiple tabs:

- Summary statistics on biogas adoption and usage
- Health and sanitation impacts
- Socio-economic benefits
- Technical performance metrics
- User satisfaction rates
- Gender impact analysis
- Agricultural system changes
- Environmental benefits and carbon emission reductions

Use the sidebar filters to customize the data view by province, gender, and other parameters as needed.