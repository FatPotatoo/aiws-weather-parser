<?php
require_once 'config/database.php';
$database = new Database();
$db = $database->getConnection();

$date_filter = $_GET['date_filter'] ?? '';
$pairs = $_GET['pairs'] ?? [];

$query = "
SELECT we.id, we.entry_date, ws.id as system_id, ws.weather_system, pl.level_name, s.subdivision_name
FROM weather_entries we
JOIN weather_systems ws ON we.id = ws.entry_id
JOIN pressure_levels pl ON ws.id = pl.system_id
JOIN subdivisions s ON ws.id = s.system_id
WHERE 1=1";

$params = [];

if (!empty($date_filter)) {
    $query .= " AND we.entry_date = :entry_date";
    $params[':entry_date'] = $date_filter;
}

$pairConditions = [];
foreach ($pairs as $i => $pair) {
    if (!empty($pair['system']) || !empty($pair['subdivision'])) {
        $conds = [];

        // SYSTEM filter
        if (!empty($pair['system'])) {
            $sysKey = ":pair_system_$i";
            $conds[] = "ws.weather_system LIKE $sysKey";
            $params[$sysKey] = '%' . trim($pair['system']) . '%';
        }

        // MULTIPLE SUBDIVISIONS filter (comma-separated)
        if (!empty($pair['subdivision'])) {
            $subdivisions = array_map('trim', explode(',', $pair['subdivision']));
            $orSubConds = [];
            foreach ($subdivisions as $j => $sub) {
                // Use only alphanumeric-safe keys
                $subKey = ":subdiv_{$i}_{$j}";
                $orSubConds[] = "s.subdivision_name LIKE $subKey";
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



$query .= " ORDER BY we.entry_date DESC, ws.weather_system, pl.level_name";
$stmt = $db->prepare($query);
$stmt->execute($params);

$data = [];
$systemList = [];
$subdivisionList = [];
$systemToSubdivision = [];

while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $date = $row['entry_date'];
    $system = $row['weather_system'];
    $system_id = $row['system_id'];
    $pressure = $row['level_name'];
    $sub = $row['subdivision_name'];

    $systemList[$system] = true;
    $subdivisionList[$sub] = true;
    $systemToSubdivision[$system][] = $sub;

    if (!isset($data[$date])) $data[$date] = [];
    if (!isset($data[$date][$system_id])) {
        $data[$date][$system_id] = [
            'system' => $system,
            'pressures' => [],
            'subdivisions' => [],
            'system_id' => $system_id
        ];
    }

    if (!in_array($pressure, $data[$date][$system_id]['pressures'])) {
        $data[$date][$system_id]['pressures'][] = $pressure;
    }
    if (!in_array($sub, $data[$date][$system_id]['subdivisions'])) {
        $data[$date][$system_id]['subdivisions'][] = $sub;
    }
}

foreach ($systemToSubdivision as &$subs) {
    $subs = array_values(array_unique($subs));
}

$systemOptions = json_encode(array_keys($systemList));
$subdivisionOptions = json_encode(array_keys($subdivisionList));
$systemToSubdivisionJson = json_encode($systemToSubdivision);
?>

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Weather Data View</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/@tarekraafat/autocomplete.js@10.2.7/dist/css/autoComplete.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100">

<!-- Sidebar -->
<button onclick="toggleSidebar()" class="text-3xl m-4 z-50 fixed top-4 left-4 md:hidden">☰</button>
<div id="sidebar" class="fixed top-0 left-0 h-full w-64 bg-blue-900 text-white p-6 shadow-lg transform -translate-x-full md:translate-x-0 transition-transform duration-300 z-40">
  <div class="flex justify-between items-center mb-6">
    <h2 class="text-xl font-bold">Navigation</h2>
    <button class="md:hidden text-white text-2xl" onclick="toggleSidebar()">×</button>
  </div>
  <nav class="flex flex-col space-y-3">
    <a href="homepage.html" class="hover:underline block">🏠 Homepage</a>
    <a href="index.php" class="hover:underline block">✍️ Data Entry</a>
    <a href="view_data.php" class="hover:underline font-semibold text-yellow-300 block">📄 View Data</a>
  </nav>
</div>

<main class="flex-1 p-8 md:ml-64">
  <div class="mb-6 flex justify-end">
<a id="exportLink"
   href="#"
   class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-800 transition"
   onclick="downloadCSV(event)">
   Export Filtered as CSV
</a>

</div>


  <h1 class="text-3xl font-bold text-blue-900 mb-6">Weather Data Records</h1>

  <form method="GET" class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8" id="filterForm">
    <input type="date" name="date_filter" value="<?= htmlspecialchars($date_filter) ?>" class="border p-2 rounded">
    <div class="col-span-1 md:col-span-3">
      <label class="block font-medium text-blue-600">System & Subdivision Pairs:</label>
      <div class="space-y-2" id="filter-pairs">
        <?php if (!empty($pairs)): ?>
          <?php foreach ($pairs as $i => $pair): ?>
            <div class="flex gap-2 items-center">
              <input name="pairs[<?= $i ?>][system]" value="<?= htmlspecialchars($pair['system']) ?>" class="border p-2 rounded w-1/2 filter-input system-type text-black placeholder-gray-400" placeholder="e.g. Depression">
              <input name="pairs[<?= $i ?>][subdivision]" value="<?= htmlspecialchars($pair['subdivision']) ?>" class="border p-2 rounded w-1/2 filter-input subdivision-type text-black placeholder-gray-400" placeholder="e.g. Kerala, Odisha, Tamil Nadu" >
              <button type="button" onclick="removeFilterPair(this)" class="text-red-600 text-xl">−</button>
            </div>
          <?php endforeach; ?>
        <?php else: ?>
         <div class="flex gap-2 items-center">
  <input type="text" name="pairs[0][system]" class="border p-2 rounded w-1/2 filter-input system-type text-black placeholder-gray-400" placeholder="e.g. Depression" />
  <input type="text" name="pairs[0][subdivision]" class="border p-2 rounded w-1/2 filter-input subdivision-type text-black placeholder-gray-400" placeholder="e.g. Kerala, Odisha, Tamil Nadu"  />
</div>

        <?php endif; ?>
      </div>
      <button type="button" onclick="addFilterPair()" class="mt-2 text-blue-600 hover:underline text-sm">+ Add More Filters</button>
    </div>
    <div class="col-span-1 md:col-span-3 flex gap-4">
      <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded">Apply Filters</button>
      <a href="view_data.php" class="bg-gray-500 text-white px-4 py-2 rounded">Clear</a>
    </div>
  </form>

  <?php foreach ($data as $date => $systems): ?>
    <div class="bg-white shadow-md rounded p-6 mb-8">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-lg font-bold text-purple-800">📅 Date: <?= htmlspecialchars($date) ?></h2>
        <a href="export_csv.php?date=<?= urlencode($date) ?>" class="text-green-600 font-semibold hover:underline">Export CSV</a>
      </div>
      <?php $count = 1; ?>
      <?php foreach ($systems as $sys): ?>
        <div class="ml-4 mb-4 border-l-4 border-blue-500 pl-4">
          <div class="flex justify-between items-center">
            <h3 class="text-md font-semibold text-blue-700">System <?= $count++ ?>: <?= htmlspecialchars($sys['system']) ?></h3>
            <div class="flex gap-3 text-sm">
              <a href="edit.php?system_id=<?= $sys['system_id'] ?>" class="text-blue-600 hover:underline">Edit</a>
              <a href="delete.php?system_id=<?= $sys['system_id'] ?>" class="text-red-600 hover:underline" onclick="return confirm('Are you sure?')">Delete</a>
            </div>
          </div>
          <p class="ml-6 text-gray-800"><strong>Pressure:</strong> <?= implode(', ', $sys['pressures']) ?></p>
          <p class="ml-6 text-gray-800"><strong>Subdivisions:</strong> <?= implode(', ', $sys['subdivisions']) ?></p>
        </div>
      <?php endforeach; ?>
    </div>
  <?php endforeach; ?>
</main>

<script src="https://cdn.jsdelivr.net/npm/@tarekraafat/autocomplete.js@10.2.7/dist/js/autoComplete.min.js"></script>
<script>
const systemOptions = <?= $systemOptions ?>;
const subdivisionOptions = <?= $subdivisionOptions ?>;
const systemToSubdivision = <?= $systemToSubdivisionJson ?>;

function initAutocomplete() {
  document.querySelectorAll('.system-type').forEach(systemInput => {
    if (systemInput.dataset.bound) return;
    systemInput.dataset.bound = true;

    new autoComplete({
      selector: () => systemInput,
      data: { src: systemOptions },
      threshold: 0,
      debounce: 100,
      cache: false,
      onSelection: feedback => {
        systemInput.value = feedback.selection.value;
        systemInput.dispatchEvent(new Event('input'));

        const subInput = systemInput.closest('.flex').querySelector('.subdivision-type');
        if (subInput) {
          subInput.value = '';
          bindSubdivisionAutocomplete(subInput); // Rebind with updated system
        }

        const inputs = Array.from(document.querySelectorAll('.filter-input'));
        const index = inputs.indexOf(systemInput);
        const next = inputs[index + 1];
        if (next) next.focus();
      }
    });
  });

  document.querySelectorAll('.subdivision-type').forEach(subInput => {
    if (subInput.dataset.bound) return;
    subInput.dataset.bound = true;
    bindSubdivisionAutocomplete(subInput);
  });
}

function bindSubdivisionAutocomplete(subInput) {
  const systemInput = subInput.closest('.flex')?.querySelector('.system-type');

  new autoComplete({
    selector: () => subInput,
    data: {
      src: () => {
        const selectedSystem = systemInput?.value?.trim();
        return selectedSystem && systemToSubdivision[selectedSystem]
          ? systemToSubdivision[selectedSystem]
          : subdivisionOptions;
      },
      cache: false
    },
    threshold: 0,
    debounce: 100,
    onSelection: feedback => {
      subInput.value = feedback.selection.value;
      subInput.dispatchEvent(new Event('input'));

      const inputs = Array.from(document.querySelectorAll('.filter-input'));
      const index = inputs.indexOf(subInput);
      const next = inputs[index + 1];
      if (next) next.focus();
    }
  });
}


function addFilterPair() {
  const index = document.querySelectorAll('#filter-pairs .flex').length;
  const pairDiv = document.createElement('div');
  pairDiv.className = 'flex gap-2 items-center';
  pairDiv.innerHTML = `
    <input name="pairs[${index}][system]" placeholder="e.g. Cyclonic Storm" class="border p-2 rounded w-1/2 filter-input system-type placeholder-gray-400 text-black" />
    <input name="pairs[${index}][subdivision]" placeholder="e.g. Kerala, Odisha, Tamil Nadu" class="border p-2 rounded w-1/2 filter-input subdivision-type placeholder-gray-400 text-black" />
    <button type="button" onclick="removeFilterPair(this)" class="text-red-600 text-xl">&minus;</button>
  `;
  document.getElementById('filter-pairs').appendChild(pairDiv);
  initAutocomplete(); // Re-bind autocompletes
}


function removeFilterPair(btn) {
  const parent = btn.closest('.flex');
  if (parent) parent.remove();
}

document.addEventListener('DOMContentLoaded', () => {
  initAutocomplete();

  // Generate export link based on filters
  const exportBtn = document.getElementById('exportLink');
  const filterForm = document.getElementById('filterForm');
  
  function updateExportLink() {
    const formData = new FormData(filterForm);
    const params = new URLSearchParams();

    for (const [key, value] of formData.entries()) {
      params.append(key, value);
    }

    exportBtn.href = `export_csv.php?${params.toString()}`;
  }
 // Call it once initially
  updateExportLink();

  // Then update when form changes
  filterForm.addEventListener('input', updateExportLink);
  
});

</script>
<script>
function downloadCSV(e) {
  e.preventDefault();

  const form = document.getElementById('filterForm');
  const formData = new FormData(form);
  const params = new URLSearchParams();

  for (const [key, value] of formData.entries()) {
    params.append(key, value);
  }

  // Trigger download using a hidden link
  const a = document.createElement('a');
  a.href = `export_csv.php?${params.toString()}`;
  a.download = ''; // Let browser handle file
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

</script>


</body>
</html>