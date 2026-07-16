<?php
// Enable error reporting
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection(); // Returns a mysqli connection

$system_id = $_GET['system_id'] ?? null;

if ($system_id) {
    // MySQLi query using '?' placeholder
    $stmt = $db->prepare("DELETE FROM weather_system_entries WHERE id = ?");
    $stmt->bind_param("i", $system_id);
    $stmt->execute();
}

header("Location: view_data.php");
exit;
?>
