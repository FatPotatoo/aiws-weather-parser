<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$system_id = $_GET['system_id'] ?? null;

// Delete pressure levels
$stmt = $db->prepare("DELETE FROM pressure_levels WHERE system_id = :id");
$stmt->execute([':id' => $system_id]);

// Delete subdivisions
$stmt = $db->prepare("DELETE FROM subdivisions WHERE system_id = :id");
$stmt->execute([':id' => $system_id]);

// Delete system
$stmt = $db->prepare("DELETE FROM weather_systems WHERE id = :id");
$stmt->execute([':id' => $system_id]);

header("Location: view_data.php");
exit;
?>
