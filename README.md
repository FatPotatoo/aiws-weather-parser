
# Weather Data Management System - PHP/MySQL Version

## Setup Instructions

### 1. Database Setup
1. Create a MySQL database
2. Import the SQL schema from `database/weather_data.sql`
3. Update database credentials in `config/database.php`

### 2. File Structure
```
weather-system/
├── config/
│   └── database.php          # Database configuration
├── classes/
│   ├── WeatherEntry.php      # Weather entry model
│   └── WeatherSystem.php     # Weather system model
├── database/
│   └── weather_data.sql      # Database schema
├── js/
│   └── weather_form.js       # Frontend JavaScript
├── index.php                 # Main form page
├── view_data.php             # Data viewing page
├── process_form.php          # Form processing
├── export_csv.php            # CSV export functionality
└── README.md                 # This file
```

### 3. Configuration
Edit `config/database.php` and update:
- `$host`: Your MySQL host (usually 'localhost')
- `$db_name`: Your database name
- `$username`: Your MySQL username
- `$password`: Your MySQL password

### 4. Features
- **Data Entry**: Add weather data with multiple systems, pressure levels, and subdivisions
- **Data Viewing**: View all entries with filtering capabilities
- **Search & Filter**: Filter by date, weather system, or subdivision
- **Data Export**: Export filtered data to CSV
- **Responsive Design**: Works on desktop and mobile devices

### 5. Usage
1. Open `index.php` to add new weather data entries
2. Select date and add weather systems with their details
3. Use `view_data.php` to view and manage existing data
4. Apply filters to find specific entries
5. Export data using the CSV export functionality

### 6. Database Schema
- `weather_entries`: Main entries with dates
- `weather_systems`: Weather system details for each entry
- `pressure_levels`: Pressure levels for each system
- `subdivisions`: Geographic subdivisions for each system
- `output_csv_entries`: Parsed rows from generated/processed output CSV files

### 7. Security Features
- PDO prepared statements to prevent SQL injection
- Input validation and sanitization
- Transaction support for data integrity
