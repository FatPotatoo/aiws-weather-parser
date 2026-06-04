<?php
require_once 'config/database.php';

if ($_POST) {
    $database = new Database();
    $db = $database->getConnection();

    if (!$db) {
        header("Location: index.php?error=connection");
        exit();
    }

    try {
        if (!$db->inTransaction()) {
            $db->beginTransaction();
        }

        $stmt = $db->prepare(
            "INSERT INTO Weather_System_Entries (entry_date, weather_system, subdivisions, pressure_level) " .
            "VALUES (:entry_date, :weather_system, :subdivisions, :pressure_level)"
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

                $stmt->execute([
                    ':entry_date' => $entry_date,
                    ':weather_system' => $weather_system,
                    ':subdivisions' => $subdivisions,
                    ':pressure_level' => $pressure_level,
                ]);
            }
        }

        $db->commit();

        header("Location: index.php?success=1");
        exit();

    } catch (Exception $e) {
        if ($db && $db->inTransaction()) {
            $db->rollBack();
        }
        echo "Error: " . $e->getMessage();
    }
} else {
    header("Location: index.php");
    exit();
}
?>
