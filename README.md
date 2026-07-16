# Advanced Weather Data Management & Analytics System

An integrated web application built for the India Meteorological Department (IMD) to extract, store, map, and analyze daily weather bulletins. The system leverages Large Language Models (LLMs) for automated text extraction, hosts a custom Python Web GIS HTTP server for NetCDF rainfall mapping, and provides vector space (TF-IDF + Cosine Similarity) modeling for historical weather pattern comparisons.

---

## 🛠️ Localhost Setup Instructions (XAMPP / Local Server)

To run this application locally on your computer (Windows, macOS, or Linux), follow these steps:

### 1. Web Server Setup (XAMPP)
1.  Download and install [XAMPP](https://www.apachefriends.org/).
2.  Move the project folder `aiws-weather-parser` into your XAMPP web root directory:
    *   **Windows**: `C:\xampp\htdocs\aiws-weather-parser`
    *   **Linux**: `/opt/lampp/htdocs/aiws-weather-parser`
    *   **macOS**: `/Applications/XAMPP/htdocs/aiws-weather-parser`
3.  Open the **XAMPP Control Panel** and start both **Apache** and **MySQL**.

### 2. Database Import
1.  Open your browser and navigate to `http://localhost/phpmyadmin/`.
2.  Create a new database named `weather_data_systems`.
3.  Select the `weather_data_systems` database, click the **Import** tab, choose the `weather_data_system.sql` dump file from the project, and click **Go**.
4.  Configure your credentials in `config/database.php`:
    ```php
    private $host = 'localhost';
    private $db_name = 'weather_data_systems';
    private $username = 'root'; // Default XAMPP user
    private $password = '';     // Default XAMPP password is empty
    ```

### 3. Running the Python GIS Server
The **Rainfall Map Viewer** relies on a background Python server to parse NetCDF files:
1.  Install the required Python packages:
    ```bash
    pip install netCDF4 numpy
    ```
2.  Navigate to the `RainfallMapper` directory and run the server on port `8000`:
    *   **Linux/macOS**:
        ```bash
        python3 extract_rainfall.py --server
        ```
    *   **Windows (Command Prompt / PowerShell)**:
        ```cmd
        python extract_rainfall.py --server
        ```

### 4. Supply Fireworks API Key (For LLM Extractor)
Since the API key has been removed from global system environment variables, you must supply it whenever you run the LLM extraction runner.

*   **Option A: Temporary Terminal Session (Recommended)**
    Set the variable inside your terminal before running the script:
    *   **Linux/macOS**:
        ```bash
        export FIREWORKS_API_KEY="your_api_key_here"
        python3 runner.py
        ```
    *   **Windows PowerShell**:
        ```powershell
        $env:FIREWORKS_API_KEY="your_api_key_here"
        python runner.py
        ```
    *   **Windows Command Prompt (CMD)**:
        ```cmd
        set FIREWORKS_API_KEY=your_api_key_here
        python runner.py
        ```

*   **Option B: Local `.env` Configuration**
    Install `python-dotenv` and place a `.env` file in the `fireworks-weather-extractor` folder containing:
    ```text
    FIREWORKS_API_KEY=your_api_key_here
    ```

---

## 🌟 Core Features

The application revolves around 3 primary modules:

### 📡 Feature 1: Interactive Data Portal (PHP / MySQLi)
A complete system to input, inspect, and manage historical weather data:
*   **Data Entry Form (`index.php`)**: Allows manual entry of weather observations. Users can dynamically add multiple weather systems per day, specifying the system name, vertical pressure levels (heights), and geographical subdivisions.
*   **Records Explorer (`view_data.php`)**: A query dashboard supporting complex searches. It allows users to filter records using **System & Subdivision Pairs** (e.g., finding days containing both a *Western Disturbance in Jammu & Kashmir* AND a *Depression in the Arabian Sea*). The interface displays all observed weather systems for matching dates.
*   **Actions (`edit.php` / `delete.php` / `export_csv.php`)**: Allows instant editing or deletion of records, and exporting the filtered dataset directly into a standardized CSV file.

### 🗺️ Feature 2: Rainfall GIS Mapper (Leaflet + NetCDF)
Visualizes spatial meteorological rainfall observations over the Indian subcontinent:
*   **NetCDF Parser**: The Python background server reads `.nc` datasets (meteorological grid files) and extracts geographical lat/lon points and precipitation values.
*   **Leaflet Visualization (`RainfallMapper/index.html`)**: When viewing a record's rainfall map, the app queries the local python server for that date and overlays a custom color-mapped grid directly onto the map. Clicking on grid cells displays local rainfall in millimeters.

### 🔍 Feature 3: Weather Pattern Similarity Engine (TF-IDF + Cosine Similarity)
Allows forecasters to find historical weather patterns that resemble a current layout:
*   **Date Selector (`similarity_query.php`)**: Uses Flatpickr to present a calendar that fetches all unique dates from your database. Dates that do not have recorded weather data are automatically grayed out and unclickable.
*   **Vector Comparisons (`query_similar.py`)**: When a target date is selected, the system builds text vectors (TF-IDF) of the weather systems, pressure heights, and subdivisions observed on that day. It then runs Cosine Similarity against all other days in the database to retrieve the **Top 5 most similar historical days** in seconds, showing a confidence match percentage.

---

## 💡 Troubleshooting

### OPcache Invalidation (Linux Servers)
To clear the PHP bytecode cache on a production server without restarting Apache, run this script via your browser:
```text
http://<server-ip>/aiws-weather-parser/clear_cache.php
```

### Table Casing
Ensure MySQL table casing matches exactly. The default tables are:
*   `weather_system_entries` (or `Weather_System_Entries` depending on SQL collation).
