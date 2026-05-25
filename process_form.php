
<?php
require_once 'config/database.php';
require_once 'classes/WeatherEntry.php';
require_once 'classes/WeatherSystem.php';

if ($_POST) {
    $database = new Database();
    $db = $database->getConnection();
    
    try {
        $db->beginTransaction();
        
        // Create weather entry
        $weather_entry = new WeatherEntry($db);
        $weather_entry->entry_date = $_POST['entry_date'];
        $entry_id = $weather_entry->create();
        
        if ($entry_id && isset($_POST['weather_systems'])) {
            $weather_system = new WeatherSystem($db);
            
            foreach ($_POST['weather_systems'] as $system_number => $system_data) {
                if (!empty($system_data['system']) || !empty($system_data['levels']) || !empty($system_data['subdivisions'])) {
                    // Create weather system
                    $weather_system->entry_id = $entry_id;
                    $weather_system->system_number = $system_number;
                    $weather_system->weather_system = $system_data['system'] ?? '';
                    
                    $system_id = $weather_system->create();
                    
                    if ($system_id) {
                        // Add pressure levels
                        if (!empty($system_data['levels'])) {
                            foreach ($system_data['levels'] as $level) {
                                $weather_system->addPressureLevel($system_id, $level);
                            }
                        }
                        
                        // Add subdivisions
                        if (!empty($system_data['subdivisions'])) {
                            foreach ($system_data['subdivisions'] as $subdivision) {
                                $weather_system->addSubdivision($system_id, $subdivision);
                            }
                        }
                    }
                }
            }
        }
        
        $db->commit();
        
        // Redirect with success message
        header("Location: index.php?success=1");
        exit();
        
    } catch (Exception $e) {
        $db->rollback();
        echo "Error: " . $e->getMessage();
    }
} else {
    header("Location: index.php");
    exit();
}
?>
