<?php
// Enable error reporting for troubleshooting
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

require_once 'config/database.php';

if ($_POST) {
    $database = new Database();
    $db = $database->getConnection(); // Returns a mysqli connection

    if (!$db) {
        header("Location: index.php?error=connection");
        exit();
    }

    try {
        // Start transaction in MySQLi
        $db->begin_transaction();

        // MySQLi uses '?' placeholders
        $stmt = $db->prepare(
            "INSERT INTO weather_system_entries (entry_date, weather_system, subdivisions, height) VALUES (?, ?, ?, ?)"
        );

        $entry_date = $_POST['entry_date'];

        if (!empty($_POST['weather_systems']) && is_array($_POST['weather_systems'])) {
            foreach ($_POST['weather_systems'] as $system_data) {
                if (empty($system_data['system']) && empty($system_data['levels']) && empty($system_data['subdivisions'])) {
                    continue;
                }

                $weather_system = $system_data['system'] ?? '';
                $subdivisions = !empty($system_data['subdivisions']) && is_array($system_data['subdivisions'])
                    ? implode(', ', $system_data['subdivisions'])
                    : null;
                $pressure_level = !empty($system_data['levels']) && is_array($system_data['levels'])
                    ? implode(', ', $system_data['levels'])
                    : null;

                // Bind parameters and execute
                $stmt->bind_param("ssss", $entry_date, $weather_system, $subdivisions, $pressure_level);
                $stmt->execute();
            }
        }

        $db->commit();

        header("Location: index.php?success=1");
        exit();

    } catch (Exception $e) {
        $db->rollback();
        echo "Error: " . $e->getMessage();
    }
} else {
    header("Location: index.php");
    exit();
}
?>
