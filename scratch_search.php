<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();
if ($db) {
    $q = $db->query("SELECT * FROM Weather_System_Entries WHERE weather_system LIKE '%depression%' OR weather_system LIKE '%dep%'");
    $rows = $q->fetchAll(PDO::FETCH_ASSOC);
    echo "Total DB matches: " . count($rows) . "\n";
    foreach (array_slice($rows, 0, 10) as $r) {
        echo "Date: {$r['entry_date']} | System: {$r['weather_system']} | Heights: {$r['height']} | Subdivisions: {$r['subdivisions']}\n";
    }
}
?>
