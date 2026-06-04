<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$system_id = $_GET['system_id'] ?? null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $new_name = $_POST['weather_system'] ?? '';

    $stmt = $db->prepare("UPDATE Weather_System_Entries SET weather_system = :name WHERE id = :id");
    $stmt->execute([
        ':name' => $new_name,
        ':id' => $system_id
    ]);

    header("Location: view_data.php");
    exit;
}

$stmt = $db->prepare("SELECT weather_system FROM Weather_System_Entries WHERE id = :id");
$stmt->execute([':id' => $system_id]);
$row = $stmt->fetch(PDO::FETCH_ASSOC);
?>

<!DOCTYPE html>
<html>
<head><title>Edit Weather System</title></head>
<body>
  <h2>Edit Weather System</h2>
  <form method="POST">
    <label>Weather System:</label>
    <input type="text" name="weather_system" value="<?= htmlspecialchars($row['weather_system']) ?>" required>
    <button type="submit">Save</button>
  </form>
</body>
</html>
