<?php
class Database {
    private $host = 'localhost';
    private $db_name = 'weather_data_system';
    private $username = 'root'; // Change this to your MySQL username
    private $password = '';     // Change this to your MySQL password
    private $conn;

    public function getConnection() {
        $this->conn = null;
        
        $json_path = __DIR__ . '/database.json';
        if (file_exists($json_path)) {
            $config = json_decode(file_get_contents($json_path), true);
            if ($config) {
                $this->host = $config['DB_HOST'] ?? $this->host;
                $this->db_name = $config['DB_NAME'] ?? $this->db_name;
                $this->username = $config['DB_USER'] ?? $this->username;
                $this->password = $config['DB_PASSWORD'] ?? $this->password;
                
                // If a specific port is provided, append it to the host
                if (!empty($config['DB_PORT'])) {
                    $this->host .= ';port=' . $config['DB_PORT'];
                }
            }
        }
        
        try {
            $this->conn = new PDO(
                "mysql:host=" . $this->host . ";dbname=" . $this->db_name,
                $this->username,
                $this->password
            );
            $this->conn->exec("set names utf8");
            $this->conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        } catch(PDOException $exception) {
            echo "Connection error: " . $exception->getMessage();
        }
        
        return $this->conn;
    }
}
?>
