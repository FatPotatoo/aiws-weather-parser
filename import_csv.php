<?php
require_once 'config/database.php';

$csv_file = 'output_aiws_corrected_subdivisions.csv';

if (!file_exists($csv_file)) {
    die("CSV file not found: $csv_file\n");
}

$database = new Database();
$db = $database->getConnection();

if (!$db) {
    die("Database connection failed\n");
}

$handle = fopen($csv_file, 'r');
if (!$handle) {
    die("Could not open CSV file\n");
}

// Read header
$header = fgetcsv($handle);

$count = 0;
$errors = 0;

try {
    if (!$db->inTransaction()) {
        $db->beginTransaction();
    }

    $stmt = $db->prepare(
        "INSERT INTO Weather_System_Entries (entry_date, weather_system, subdivisions, pressure_level) " .
        "VALUES (:entry_date, :weather_system, :subdivisions, :pressure_level)"
    );

    while (($row = fgetcsv($handle)) !== false) {
        // Map CSV columns to array
        $data = array_combine($header, $row);

        // Convert date from DD-MM-YYYY to YYYY-MM-DD
        $date_parts = explode('-', $data['date']);
        if (count($date_parts) === 3) {
            $entry_date = "{$date_parts[2]}-{$date_parts[1]}-{$date_parts[0]}";
        } else {
            echo "Skipping row with invalid date: {$data['date']}\n";
            continue;
        }

        $weather_system = trim($data['weather_system'] ?? '');
        $subdivisions = trim($data['subdivisions'] ?? '') ?: null;
        $pressure_level = trim($data['pressure_level'] ?? '') ?: null;

        try {
            $stmt->execute([
                ':entry_date' => $entry_date,
                ':weather_system' => $weather_system,
                ':subdivisions' => $subdivisions,
                ':pressure_level' => $pressure_level,
            ]);
            $count++;
        } catch (Exception $e) {
            $errors++;
            echo "Error on row: {$e->getMessage()}\n";
        }
    }

    $db->commit();
    fclose($handle);

    echo "Import completed!\n";
    echo "Successfully inserted: $count rows\n";
    echo "Errors: $errors\n";

} catch (Exception $e) {
    if ($db && $db->inTransaction()) {
        $db->rollBack();
    }
    fclose($handle);
    die("Transaction error: {$e->getMessage()}\n");
}
?>
