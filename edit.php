<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$system_id = $_GET['system_id'] ?? null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $new_name = $_POST['weather_system'] ?? '';
    $entry_date = $_POST['entry_date'] ?? '';
    $subdivisions = $_POST['subdivisions'] ?? '';
    $pressure_level = $_POST['pressure_level'] ?? '';

    $stmt = $db->prepare("UPDATE Weather_System_Entries SET weather_system = :name, entry_date = :date, subdivisions = :subdivisions, pressure_level = :pressure_level WHERE id = :id");
    $stmt->execute([
        ':name' => $new_name,
        ':date' => $entry_date,
        ':subdivisions' => $subdivisions,
        ':pressure_level' => $pressure_level,
        ':id' => $system_id
    ]);

    header("Location: view_data.php");
    exit;
}

$stmt = $db->prepare("SELECT entry_date, weather_system, subdivisions, pressure_level FROM Weather_System_Entries WHERE id = :id");
$stmt->execute([':id' => $system_id]);
$row = $stmt->fetch(PDO::FETCH_ASSOC);
?>

<!DOCTYPE html>
<html>
<head>
  <title>Edit Weather System</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100">
  <div class="max-w-2xl mx-auto p-8 bg-white rounded-lg shadow mt-8">
    <h2 class="text-2xl font-bold mb-6">Edit Weather System</h2>
    <form method="POST" class="space-y-4">
      <div>
        <label class="block font-medium text-gray-700 mb-2">Entry Date:</label>
        <input type="date" name="entry_date" value="<?= htmlspecialchars($row['entry_date'] ?? '') ?>" class="w-full border p-2 rounded text-black" required>
      </div>
      
      <div>
        <label class="block font-medium text-gray-700 mb-2">Weather System:</label>
        <input type="text" name="weather_system" value="<?= htmlspecialchars($row['weather_system'] ?? '') ?>" class="w-full border p-2 rounded text-black" required>
      </div>

      <div>
        <label class="block font-medium text-gray-700 mb-2">Subdivisions (comma-separated):</label>
        <input type="text" name="subdivisions" value="<?= htmlspecialchars($row['subdivisions'] ?? '') ?>" class="w-full border p-2 rounded text-black" placeholder="e.g. Kerala, Tamil Nadu, Odisha">
      </div>

      <div>
        <label class="block font-medium text-gray-700 mb-2">Pressure Level (comma-separated):</label>
        <input type="text" name="pressure_level" value="<?= htmlspecialchars($row['pressure_level'] ?? '') ?>" class="w-full border p-2 rounded text-black" placeholder="e.g. 925, 850 hPa or Surface">
      </div>

      <div class="flex gap-3 mt-6">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-800">Save</button>
        <a href="view_data.php" class="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-700">Cancel</a>
      </div>
    </form>
  </div>
</body>
</html>

