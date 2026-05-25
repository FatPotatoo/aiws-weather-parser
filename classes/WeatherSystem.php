
<?php
class WeatherSystem {
    private $conn;
    private $table_name = "weather_systems";

    public $id;
    public $entry_id;
    public $system_number;
    public $weather_system;

    public function __construct($db) {
        $this->conn = $db;
    }

    public function create() {
        $query = "INSERT INTO " . $this->table_name . " (entry_id, system_number, weather_system) VALUES (:entry_id, :system_number, :weather_system)";
        $stmt = $this->conn->prepare($query);
        
        $stmt->bindParam(":entry_id", $this->entry_id);
        $stmt->bindParam(":system_number", $this->system_number);
        $stmt->bindParam(":weather_system", $this->weather_system);
        
        if($stmt->execute()) {
            return $this->conn->lastInsertId();
        }
        return false;
    }

    public function addPressureLevel($system_id, $level) {
        $query = "INSERT INTO pressure_levels (system_id, level_name) VALUES (:system_id, :level_name)";
        $stmt = $this->conn->prepare($query);
        $stmt->bindParam(":system_id", $system_id);
        $stmt->bindParam(":level_name", $level);
        return $stmt->execute();
    }

    public function addSubdivision($system_id, $subdivision) {
        $query = "INSERT INTO subdivisions (system_id, subdivision_name) VALUES (:system_id, :subdivision_name)";
        $stmt = $this->conn->prepare($query);
        $stmt->bindParam(":system_id", $system_id);
        $stmt->bindParam(":subdivision_name", $subdivision);
        return $stmt->execute();
    }
}
?>
