<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$date_filter = $_GET['date'] ?? ($_GET['date_filter'] ?? '');

$pairs = $_GET['pairs'] ?? [];

// Initial query
$query = "
SELECT id AS system_id, entry_date, weather_system, pressure_level, subdivisions, created_at
FROM Weather_System_Entries
WHERE 1=1
";

$params = [];

// Date filter
if (!empty($date_filter)) {
    $query .= " AND entry_date = :entry_date";
    $params[':entry_date'] = $date_filter;
}

// Pairs filter
$pairConditions = [];
foreach ($pairs as $i => $pair) {
    if (!empty($pair['system']) || !empty($pair['subdivision'])) {
        $conds = [];

        if (!empty($pair['system'])) {
            $sysKey = ":pair_system_$i";
            $conds[] = "weather_system LIKE $sysKey";
            $params[$sysKey] = '%' . trim($pair['system']) . '%';
        }

        if (!empty($pair['subdivision'])) {
            $subdivisions = array_map('trim', explode(',', $pair['subdivision']));
            $orSubConds = [];
            foreach ($subdivisions as $j => $sub) {
                $subKey = ":subdiv_{$i}_{$j}";
                $orSubConds[] = "subdivisions LIKE $subKey";
                $params[$subKey] = '%' . $sub . '%';
            }
            if (!empty($orSubConds)) {
                $conds[] = '(' . implode(' OR ', $orSubConds) . ')';
            }
        }

        if (!empty($conds)) {
            $pairConditions[] = '(' . implode(' AND ', $conds) . ')';
        }
    }
}
if (!empty($pairConditions)) {
    $query .= " AND (" . implode(" OR ", $pairConditions) . ")";
}

$query .= " ORDER BY entry_date DESC, weather_system, pressure_level";

$stmt = $db->prepare($query);
$stmt->execute($params);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Group by date → system_id
$data = [];
foreach ($rows as $row) {
    $date = $row['entry_date'];
    $sys_id = $row['system_id'];

    if (!isset($data[$date])) $data[$date] = [];
    if (!isset($data[$date][$sys_id])) {
        $data[$date][$sys_id] = [
            'weather_system' => $row['weather_system'],
            'pressures' => [],
            'subdivisions' => [],
            'created_at' => $row['created_at']
        ];
    }

    $data[$date][$sys_id]['pressures'] = array_filter(array_map('trim', explode(',', $row['pressure_level'] ?? '')));
    $data[$date][$sys_id]['subdivisions'] = array_filter(array_map('trim', explode(',', $row['subdivisions'] ?? '')));
}

// Output CSV
header('Content-Type: text/csv');
$filename = "weather_data_" . ($date_filter ?: "filtered") . ".csv";
header("Content-Disposition: attachment; filename=\"$filename\"");

$output = fopen('php://output', 'w');
fputcsv($output, ['Date', 'System Number', 'Weather System', 'Pressure Levels', 'Subdivisions', 'Created At']);

foreach ($data as $date => $systems) {
    $count = 1;
    foreach ($systems as $sys) {
        fputcsv($output, [
            $date,
            $count++,
            $sys['weather_system'],
            implode(', ', array_unique($sys['pressures'])),
            implode(', ', array_unique($sys['subdivisions'])),
            $sys['created_at']
        ]);
    }
}

fclose($output);
exit;
?>
