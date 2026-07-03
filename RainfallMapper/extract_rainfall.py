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
    
    # Dynamically select NetCDF file based on target year
    default_filename = f"RF25_ind{year}_rfp25.nc"
    nc_file = os.environ.get('NETCDF_PATH') or os.path.join(script_dir, default_filename)
    
    # Fallback to 2025 if the target year's file is not found
    if not os.path.exists(nc_file):
        fallback_file = os.path.join(script_dir, 'RF25_ind2025_rfp25.nc')
        if os.path.exists(fallback_file) and not os.environ.get('NETCDF_PATH'):
            nc_file = fallback_file
        else:
            return {"error": f"NetCDF file for year {year} not found at '{nc_file}'."}
    
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
