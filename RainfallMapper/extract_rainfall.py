import sys
import json
import os
import numpy as np
import xarray as xr
import pandas as pd

def extract_data(date_str):
    # Parse date first to determine the year
    try:
        import pandas as pd
        target_date = pd.to_datetime(date_str)
        year = target_date.year
    except Exception as e:
        return {"error": f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if NetCDF file exists for the year
    default_filename = f"RF25_ind{year}_rfp25.nc"
    nc_file = os.environ.get('NETCDF_PATH') or os.path.join(script_dir, default_filename)
    
    use_grd = False
    if not os.path.exists(nc_file):
        # Fall back to GRD if the target year's NetCDF is not found
        use_grd = True
        
    if use_grd:
        grd_dir = os.path.join(script_dir, "grd_data")
        os.makedirs(grd_dir, exist_ok=True)
        
        # Target date formatted
        year = target_date.year
        month = target_date.month
        day = target_date.day
        formatted_date_str = f"{year}-{month:02d}-{day:02d}"
        
        grd_filename = f"rain_{year}{month:02d}{day:02d}.grd"
        grd_path = os.path.join(grd_dir, grd_filename)
        
        # If it doesn't exist, download it from IMD Pune real-time gridded data
        if not os.path.exists(grd_path):
            import requests
            url = "https://imdpune.gov.in/cmpg/Realtimedata/Rainfall/rain.php"
            post_date = f"{day:02d}{month:02d}{year}"
            try:
                resp = requests.post(url, data={"rain": post_date}, timeout=20)
                if resp.status_code == 200 and len(resp.content) == 69660:
                    with open(grd_path, "wb") as f:
                        f.write(resp.content)
                else:
                    return {"error": f"Failed to download GRD file from IMD (Status: {resp.status_code}, Length: {len(resp.content)} bytes). The file might not be published yet."}
            except Exception as e:
                return {"error": f"Failed to download GRD file due to network error: {str(e)}"}
        
        try:
            raw_data = np.fromfile(grd_path, dtype='<f4')
            if len(raw_data) != 17415:
                return {"error": f"Invalid GRD file size: {len(raw_data)} floats instead of 17415"}
            
            # Reshape to (129, 135)
            rainfall = raw_data.reshape((129, 135))
            # Replace -999.0 with NaN
            rainfall = np.where(rainfall == -999.0, np.nan, rainfall)
            
            # Coordinates
            latitudes = [6.5 + i * 0.25 for i in range(129)]
            longitudes = [66.5 + j * 0.25 for j in range(135)]
            date_match_str = formatted_date_str
        except Exception as e:
            return {"error": f"Failed to parse GRD file: {str(e)}"}
            
    else:
        try:
            # Open dataset
            ds = xr.open_dataset(nc_file)
            
            # Check if date is in range
            time_values = ds['TIME'].values
            time_pd = pd.to_datetime(time_values)
            
            # Find closest date or exact date
            date_match = None
            for t in time_pd:
                if t.date() == target_date.date():
                    date_match = t
                    break
                    
            if date_match is None:
                min_date = time_pd.min().strftime('%Y-%m-%d')
                max_date = time_pd.max().strftime('%Y-%m-%d')
                return {"error": f"Date '{date_str}' is out of range. The dataset '{default_filename}' covers {min_date} to {max_date}."}
            
            # Select data for the matching date
            day_ds = ds.sel(TIME=date_match)
            
            # Extract variables
            latitudes = day_ds['LATITUDE'].values.tolist()
            longitudes = day_ds['LONGITUDE'].values.tolist()
            rainfall = day_ds['RAINFALL'].values # 2D numpy array (LATITUDE, LONGITUDE)
            date_match_str = date_match.strftime('%Y-%m-%d')
        except Exception as e:
            return {"error": f"An error occurred while processing the NetCDF file: {str(e)}"}

    try:
        # Calculate statistics over land (where rainfall is not NaN)
        land_mask = ~np.isnan(rainfall)
        land_points = rainfall[land_mask]
        
        if len(land_points) > 0:
            max_rain = float(np.max(land_points))
            mean_rain = float(np.mean(land_points))
            
            # Find coordinates of maximum rainfall
            max_idx = np.nanargmax(rainfall)
            max_row, max_col = np.unravel_index(max_idx, rainfall.shape)
            max_lat = float(latitudes[max_row])
            max_lon = float(longitudes[max_col])
            
            # Active rain area: rainfall > 0.1 mm
            rainy_points = land_points[land_points > 0.1]
            rain_area_pct = float(len(rainy_points) / len(land_points) * 100)
        else:
            max_rain = 0.0
            mean_rain = 0.0
            max_lat = 0.0
            max_lon = 0.0
            rain_area_pct = 0.0
            
        # Replace NaN values with -1.0 for easy JSON serialization and fast frontend processing
        rainfall_filled = np.nan_to_num(rainfall, nan=-1.0)
        rainfall_list = rainfall_filled.tolist()
        
        # Prepare response
        response = {
            "success": True,
            "date": date_match_str,
            "latitudes": latitudes,
            "longitudes": longitudes,
            "rainfall": rainfall_list,
            "stats": {
                "max_rainfall": round(max_rain, 2),
                "max_location": {
                    "latitude": round(max_lat, 2),
                    "longitude": round(max_lon, 2)
                },
                "mean_rainfall": round(mean_rain, 2),
                "rain_area_percentage": round(rain_area_pct, 2),
                "total_land_points": int(len(land_points))
            }
        }
        return response
        
    except Exception as e:
        return {"error": f"An error occurred while calculating statistics: {str(e)}"}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No date provided. Usage: python extract_rainfall.py YYYY-MM-DD"}))
        sys.exit(1)
        
    date_input = sys.argv[1]
    result = extract_data(date_input)
    print(json.dumps(result))
