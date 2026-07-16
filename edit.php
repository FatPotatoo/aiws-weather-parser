<?php
// Enable error reporting
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection(); // Returns a mysqli connection

$system_id = $_GET['system_id'] ?? null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $new_name = $_POST['weather_system'] ?? '';
    $entry_date = $_POST['entry_date'] ?? '';
    $subdivisions = $_POST['subdivisions'] ?? '';
    $height = $_POST['height'] ?? '';

    // MySQLi uses '?' placeholders
    $stmt = $db->prepare("UPDATE weather_system_entries SET weather_system = ?, entry_date = ?, subdivisions = ?, height = ? WHERE id = ?");
    $stmt->bind_param("ssssi", $new_name, $entry_date, $subdivisions, $height, $system_id);
    $stmt->execute();

    header("Location: view_data.php");
    exit;
}

// MySQLi query using '?' placeholder
$stmt = $db->prepare("SELECT entry_date, weather_system, subdivisions, height FROM weather_system_entries WHERE id = ?");
$stmt->bind_param("i", $system_id);
$stmt->execute();

$result = $stmt->get_result();
$row = $result->fetch_assoc();
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
        <label class="block font-medium text-gray-700 mb-2">Height (comma-separated):</label>
        <input type="text" name="height" value="<?= htmlspecialchars($row['height'] ?? '') ?>" class="w-full border p-2 rounded text-black" placeholder="e.g. 1.5 km, 5.8 km or Surface">
      </div>

      <div class="flex gap-3 mt-6">
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-800">Save</button>
        <a href="view_data.php" class="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-700">Cancel</a>
      </div>
    </form>
  </div>
</body>
</html>
