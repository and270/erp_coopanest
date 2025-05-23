import numpy as np

def calculate_iqr_filtered_average_seconds(data_seconds_list):
    if not data_seconds_list:
        return None
    
    # Convert all elements to float to ensure compatibility with numpy operations
    # and handle potential Decimal types from Django ORM if not handled before.
    try:
        data_seconds_list = [float(x) for x in data_seconds_list]
    except (ValueError, TypeError):
        # Handle cases where conversion is not possible for any element
        # Or decide on a specific error handling strategy (e.g., log and return None)
        # For now, if any conversion fails, assume data is unsuitable and return simple mean or None.
        if not data_seconds_list: # Re-check after potential modification attempt
            return None
        return np.mean(data_seconds_list) if data_seconds_list else None


    if len(data_seconds_list) < 4: # Not enough data for meaningful IQR
        return np.mean(data_seconds_list)

    q1 = np.percentile(data_seconds_list, 25)
    q3 = np.percentile(data_seconds_list, 75)
    iqr = q3 - q1

    # Handle cases where IQR is zero (e.g., all data points are identical or many are)
    # In such cases, outlier removal isn't meaningful, so return the mean.
    if iqr == 0:
        return np.mean(data_seconds_list)

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    filtered_data = [x for x in data_seconds_list if lower_bound <= x <= upper_bound]

    if not filtered_data: # If all data is filtered out, fallback to original mean
        return np.mean(data_seconds_list) 
    
    return np.mean(filtered_data)
