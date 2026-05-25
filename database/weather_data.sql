
-- Create database
CREATE DATABASE IF NOT EXISTS weather_data_system;
USE weather_data_system;

-- Create weather_entries table
CREATE TABLE IF NOT EXISTS weather_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Create weather_systems table
CREATE TABLE IF NOT EXISTS weather_systems (
    id INT AUTO_INCREMENT PRIMARY KEY,
    entry_id INT NOT NULL,
    system_number INT NOT NULL,
    weather_system VARCHAR(255),
    FOREIGN KEY (entry_id) REFERENCES weather_entries(id) ON DELETE CASCADE
);

-- Create pressure_levels table
CREATE TABLE IF NOT EXISTS pressure_levels (
    id INT AUTO_INCREMENT PRIMARY KEY,
    system_id INT NOT NULL,
    level_name VARCHAR(50) NOT NULL ,
    FOREIGN KEY (system_id) REFERENCES weather_systems(id) ON DELETE CASCADE
);

-- Create subdivisions table
CREATE TABLE IF NOT EXISTS subdivisions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    system_id INT NOT NULL,
    subdivision_name VARCHAR(255) NOT NULL,
    FOREIGN KEY (system_id) REFERENCES weather_systems(id) ON DELETE CASCADE
);

-- Insert sample data (optional)
INSERT INTO weather_entries (entry_date) VALUES ('2024-01-15');
