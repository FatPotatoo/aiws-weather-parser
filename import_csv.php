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
if ($header === false) {
    die("Unable to read CSV header\n");
}
$header = array_map('trim', $header);
if (count($header) > 0) {
    $header[0] = preg_replace('/^\xEF\xBB\xBF/', '', $header[0]);
}

$count = 0;
$errors = 0;

try {
    // Reset table so imported rows start with ID 1
    $db->exec("TRUNCATE TABLE Weather_System_Entries");

    $db->beginTransaction();

    $stmt = $db->prepare(
        "INSERT INTO Weather_System_Entries (entry_date, weather_system, subdivisions, pressure_level) " .
        "VALUES (:entry_date, :weather_system, :subdivisions, :pressure_level)"
    );

    while (($row = fgetcsv($handle)) !== false) {
        // Map CSV columns to array
        $data = array_combine($header, $row);

        if (!is_array($data) || !isset($data['date'])) {
            echo "Skipping row with missing date field" . PHP_EOL;
            continue;
        }

        $raw_date = trim($data['date']);
        $entry_date = null;
        if (preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $raw_date, $matches)) {
            $entry_date = $raw_date;
        } elseif (preg_match('/^(\d{2})-(\d{2})-(\d{4})$/', $raw_date, $matches)) {
            $entry_date = "{$matches[3]}-{$matches[2]}-{$matches[1]}";
        }

        if (!$entry_date) {
            echo "Skipping row with invalid date: {$raw_date}\n";
            continue;
        }

        $weather_system = trim($data['weather_system'] ?? '');
        $subdivisions = trim($data['subdivisions'] ?? '') ?: null;
        $pressure_level = trim($data['pressure_level'] ?? '');
        $height_km = trim($data['height_km'] ?? '');

        if (($height_km === '0' || $height_km === '0.0') && $pressure_level === '') {
            $pressure_level = 'Surface';
        }

        $pressure_level = $pressure_level ?: null;

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
