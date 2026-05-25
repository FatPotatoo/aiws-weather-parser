
<?php
class WeatherEntry {
    private $conn;
    private $table_name = "weather_entries";

    public $id;
    public $entry_date;
    public $created_at;

    public function __construct($db) {
        $this->conn = $db;
    }

    public function create() {
        $query = "INSERT INTO " . $this->table_name . " (entry_date) VALUES (:entry_date)";
        $stmt = $this->conn->prepare($query);
        
        $stmt->bindParam(":entry_date", $this->entry_date);
        
        if($stmt->execute()) {
            return $this->conn->lastInsertId();
        }
        return false;
    }

    public function readAll() {
        $query = "SELECT * FROM " . $this->table_name . " ORDER BY entry_date DESC";
        $stmt = $this->conn->prepare($query);
        $stmt->execute();
        return $stmt;
    }

    public function delete() {
        $query = "DELETE FROM " . $this->table_name . " WHERE id = :id";
        $stmt = $this->conn->prepare($query);
        $stmt->bindParam(":id", $this->id);
        
        return $stmt->execute();
    }

    public function getWithSystems() {
        $query = "SELECT we.*, ws.system_number, ws.weather_system,
                  GROUP_CONCAT(DISTINCT pl.level_name) as pressure_levels,
                  GROUP_CONCAT(DISTINCT s.subdivision_name) as subdivisions
                  FROM " . $this->table_name . " we
                  LEFT JOIN weather_systems ws ON we.id = ws.entry_id
                  LEFT JOIN pressure_levels pl ON ws.id = pl.system_id
                  LEFT JOIN subdivisions s ON ws.id = s.system_id
                  WHERE 1=1";
        
        $stmt = $this->conn->prepare($query);
        $stmt->execute();
        return $stmt;
    }
}
?>
