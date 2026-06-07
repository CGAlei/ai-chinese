import json

def filter_words_by_length(input_file, output_file, min_length=4):
    """
    Filter words from a JSON file, keeping only those with length >= min_length.
    
    Args:
        input_file (str): Path to input JSON file
        output_file (str): Path to output JSON file
        min_length (int): Minimum word length to keep (default: 4)
    """
    # Read the JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Filter the words list
    original_count = len(data['words'])
    filtered_words = [
        word for word in data['words'] 
        if len(word['hanzi']) >= min_length
    ]
    filtered_count = len(filtered_words)
    
    # Update the data with filtered words
    data['words'] = filtered_words
    
    # Update the date to current time
    from datetime import datetime
    data['date'] = datetime.now().isoformat()
    
    # Write the filtered data back to the output file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Print statistics
    print(f"Original word count: {original_count}")
    print(f"Filtered word count: {filtered_count}")
    print(f"Removed {original_count - filtered_count} words with less than {min_length} characters")
    print(f"Filtered data saved to: {output_file}")

# Example usage
if __name__ == "__main__":
    input_file = "maindata.json"  # Input JSON file
    output_file = "maindata_4chars.json"  # Output JSON file
    
    # Keep only words with 4 or more characters
    filter_words_by_length(input_file, output_file, min_length=4)