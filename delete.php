<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$system_id = $_GET['system_id'] ?? null;

if ($system_id) {
    $stmt = $db->prepare("DELETE FROM Weather_System_Entries WHERE id = :id");
    $stmt->execute([':id' => $system_id]);
}

header("Location: view_data.php");
exit;
?>
