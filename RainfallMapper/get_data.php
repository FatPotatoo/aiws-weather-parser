<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// Get date from GET parameter
$date = isset($_GET['date']) ? $_GET['date'] : '';

if (empty($date)) {
    echo json_encode(['error' => 'Date parameter is required.']);
    exit;
}

// Validate date format (YYYY-MM-DD)
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $date)) {
    echo json_encode(['error' => 'Invalid date format. Use YYYY-MM-DD.']);
    exit;
}

// Verify the date is in 2025
$year = explode('-', $date)[0];
if ($year !== '2025') {
    echo json_encode(['error' => 'Only dates in the year 2025 are supported.']);
    exit;
}

// Escape the date argument for command line safety
$safe_date = escapeshellarg($date);

// Execute python script to extract rainfall data
$command = "python extract_rainfall.py " . $safe_date . " 2>&1";
$output = shell_exec($command);

if ($output === null) {
    echo json_encode(['error' => 'Failed to execute the data extraction script.']);
    exit;
}

// Output the JSON response from the Python script
echo $output;
?>
