import sys
import json
import os
import numpy as np
import xarray as xr
import pandas as pd

def extract_data(date_str):
    # Resolve NetCDF path relative to this script so calls from other CWDs still work.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    nc_file = os.environ.get('NETCDF_PATH') or os.path.join(script_dir, 'RF25_ind2025_rfp25.nc')
    if not os.path.exists(nc_file):
        return {"error": f"NetCDF file '{nc_file}' not found. Ensure the file exists in {script_dir} or set NETCDF_PATH."}
    
    try:
        # Open dataset
        ds = xr.open_dataset(nc_file)
        
        # Parse date
        try:
            target_date = pd.to_datetime(date_str)
        except Exception as e:
            return {"error": f"Invalid date format: '{date_str}'. Use YYYY-MM-DD."}
        
        # Check if date is in range
        time_values = ds['TIME'].values
        time_pd = pd.to_datetime(time_values)
        
        # Find closest date or exact date
        # NetCDF dates are usually midnight, so we compare date parts
        date_match = None
        for t in time_pd:
            if t.date() == target_date.date():
                date_match = t
                break
                
        if date_match is None:
            return {"error": f"Date '{date_str}' is out of range. The dataset covers 2025-01-01 to 2025-12-31."}
        
        # Select data for the matching date
        day_ds = ds.sel(TIME=date_match)
        
        # Extract variables
        latitudes = day_ds['LATITUDE'].values.tolist()
        longitudes = day_ds['LONGITUDE'].values.tolist()
        rainfall = day_ds['RAINFALL'].values # 2D numpy array (LATITUDE, LONGITUDE)
        
        # Calculate statistics over land (where rainfall is not NaN)
        land_mask = ~np.isnan(rainfall)
        land_points = rainfall[land_mask]
        
        if len(land_points) > 0:
            max_rain = float(np.max(land_points))
            mean_rain = float(np.mean(land_points))
            
            # Find coordinates of maximum rainfall
            # nanargmax returns the flat index of the maximum value, ignoring NaNs
            max_idx = np.nanargmax(rainfall)
            max_row, max_col = np.unravel_index(max_idx, rainfall.shape)
            max_lat = float(day_ds['LATITUDE'].values[max_row])
            max_lon = float(day_ds['LONGITUDE'].values[max_col])
            
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
            "date": date_match.strftime('%Y-%m-%d'),
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
        return {"error": f"An error occurred while processing the NetCDF file: {str(e)}"}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No date provided. Usage: python extract_rainfall.py YYYY-MM-DD"}))
        sys.exit(1)
        
    date_input = sys.argv[1]
    result = extract_data(date_input)
    print(json.dumps(result))
