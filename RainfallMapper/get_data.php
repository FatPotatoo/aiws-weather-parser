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

// Verify the date is in supported years (2020 to current year)
$year = intval(explode('-', $date)[0]);
$current_year = intval(date('Y'));
if ($year < 2020 || $year > $current_year + 1) {
    echo json_encode(['error' => 'Only dates in years 2020 to ' . ($current_year + 1) . ' are supported.']);
    exit;
}

// Escape the date argument for command line safety
$safe_date = escapeshellarg($date);

// Execute python script to extract rainfall data
$command = "python extract_rainfall.py " . $safe_date . " 2>&1";
$output = shell_exec($command);

if ($output === null) {
    echo json_encode(['error' => 'Failed to execute the data extraction script. Ensure PHP can run shell commands and Python is available on PATH.']);
    exit;
}

// If the Python script printed valid JSON, forward it. Otherwise wrap the raw output as an error.
$decoded = json_decode($output, true);
if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) {
    // Forward valid JSON (already a JSON string)
    echo $output;
    exit;
}

// Not valid JSON — return structured error with the raw output (trimmed to reasonable length)
$trimmed = strlen($output) > 2000 ? substr($output, 0, 2000) . "\n...[truncated]" : $output;
echo json_encode([
    'error' => 'Data extraction script failed or returned invalid JSON.',
    'details' => $trimmed
]);
exit;
?>
