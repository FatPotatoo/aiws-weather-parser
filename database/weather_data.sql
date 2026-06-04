
-- Create database
CREATE DATABASE IF NOT EXISTS weather_data_system;
USE weather_data_system;

-- Create Weather_System_Entries table
CREATE TABLE IF NOT EXISTS Weather_System_Entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_date DATE NOT NULL,
    weather_system VARCHAR(255) NOT NULL,
    subdivisions TEXT,
    pressure_level VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_output_entry_date (entry_date),
    INDEX idx_output_weather_system (weather_system)
);

-- Insert sample data (optional)
INSERT INTO Weather_System_Entries (entry_date,  weather_system, subdivisions, pressure_level) VALUES ('2024-01-15', 'Example System', 'Example Subdivision', 'Surface');
