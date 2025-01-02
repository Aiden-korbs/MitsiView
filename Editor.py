import os
import xml.etree.ElementTree as ET
import struct

def list_files(extension):
    """List files in the current directory with a specific extension."""
    return [f for f in os.listdir('.') if f.endswith(extension)]

def select_file(extension):
    """Display a menu to select a file with the given extension."""
    files = list_files(extension)
    if not files:
        print(f"No {extension} files found in the current directory.")
        return None

    print(f"Select a {extension} file:")
    for idx, file in enumerate(files):
        print(f"{idx + 1}: {file}")

    while True:
        try:
            choice = int(input("Enter the number of your choice: ")) - 1
            if 0 <= choice < len(files):
                return files[choice]
            else:
                print("Invalid choice. Try again.")
        except ValueError:
            print("Please enter a valid number.")

def parse_xml(xml_file):
    """Parse the XML file to extract mappings and detailed table information."""
    tree = ET.parse(xml_file)
    root = tree.getroot()

    mappings = []
    for table in root.findall(".//table"):
        address = table.get("address")
        elements_x_table = table.find(".//table[@type='X Axis']")
        elements_y_table = table.find(".//table[@type='Y Axis']")

        # Extract table scaling
        table_scaling_name = table.get("scaling")
        table_scaling = None
        if table_scaling_name:
            table_scaling_element = root.find(f".//scaling[@name='{table_scaling_name}']")
            if table_scaling_element is not None:
                table_scaling = {
                    "toexpr": table_scaling_element.get("toexpr"),
                    "storagetype": table_scaling_element.get("storagetype"),
                    "endian": table_scaling_element.get("endian", "big"),
                }

        # Extract X-axis scaling
        x_scaling = None
        if elements_x_table is not None and elements_x_table.get("scaling"):
            x_scaling_name = elements_x_table.get("scaling")
            x_scaling_element = root.find(f".//scaling[@name='{x_scaling_name}']")
            if x_scaling_element is not None:
                x_scaling = {
                    "toexpr": x_scaling_element.get("toexpr"),
                    "storagetype": x_scaling_element.get("storagetype"),
                    "endian": x_scaling_element.get("endian", "big"),
                }

        # Extract Y-axis scaling
        y_scaling = None
        if elements_y_table is not None and elements_y_table.get("scaling"):
            y_scaling_name = elements_y_table.get("scaling")
            y_scaling_element = root.find(f".//scaling[@name='{y_scaling_name}']")
            if y_scaling_element is not None:
                y_scaling = {
                    "toexpr": y_scaling_element.get("toexpr"),
                    "storagetype": y_scaling_element.get("storagetype"),
                    "endian": y_scaling_element.get("endian", "big"),
                }

        # Extract the `swapxy` attribute
        swapxy = table.get("swapxy", "false").lower() == "true"

        mapping = {
            "name": table.get("name", ""),
            "address": int(address, 16) if address else 0,
            "type": table.get("type"),
            "elements_x": int(elements_x_table.get("elements", "0")) if elements_x_table is not None else 0,
            "elements_y": int(elements_y_table.get("elements", "0")) if elements_y_table is not None else 0,
            "address_x": int(elements_x_table.get("address"), 16) if elements_x_table is not None else None,
            "address_y": int(elements_y_table.get("address"), 16) if elements_y_table is not None else None,
            "scaling_x": x_scaling,
            "scaling_y": y_scaling,
            "scaling": table_scaling,
            "swapxy": swapxy,  # Include the `swapxy` attribute in the mapping
        }
        mappings.append(mapping)
    return mappings

def apply_scaling(value, scaling):
    """Apply a scaling formula (if any) to a value and round to 2 decimal places."""
    if scaling and "toexpr" in scaling:
        x = value  # Variable used in the formula
        try:
            result = eval(scaling["toexpr"])
            return round(result, 2)
        except ZeroDivisionError:
            print(f"Scaling error: Division by zero in scaling formula with value {value}")
            return 0  # Default to 0 or another fallback
        except Exception as e:
            print(f"Error applying scaling: {e}")
            return value  # Return raw value on error
    return value  # No scaling

def apply_text_color(value, min_val, max_val):
    """Apply a color gradient with 6 distinct colors to a text value."""
    if max_val - min_val == 0:
        normalized = 0  # Prevent division by zero
    else:
        normalized = (value - min_val) / (max_val - min_val)

    # Define the 6 colors in 16-bit terminal color codes
    colors = [
        "\033[31m",  # Red
        "\033[33m",  # Yellow
        "\033[32m",  # Green
        "\033[36m",  # Cyan
        "\033[34m",  # Blue
        "\033[35m",  # Magenta
    ]

    # Map normalized value to one of the 6 colors
    color_index = int(normalized * (len(colors) - 1))
    color = colors[color_index]

    # Return the value as colored text
    return f"{color}{value:.2f}\033[0m"

def decode_bin(binary_file, mappings):
    """Decode the binary file using the extracted mappings."""
    with open(binary_file, "rb") as bin_file:
        binary_data = bin_file.read()

    decoded_data = {}
    for mapping in mappings:
        try:
            # Base attributes
            address = mapping["address"]
            elements_x = mapping.get("elements_x", 0)
            elements_y = mapping.get("elements_y", 0)
            address_x = mapping.get("address_x")
            address_y = mapping.get("address_y")
            table_scaling = mapping.get("scaling")
            scaling_x = mapping.get("scaling_x", table_scaling)
            scaling_y = mapping.get("scaling_y", table_scaling)
            swap_axes = mapping.get("swapxy", False)  # Check if axes need to be swapped
            storagetype = table_scaling.get("storagetype") if table_scaling else "uint16"
            endian = ">" if table_scaling and table_scaling.get("endian") == "big" else "<"

            # Determine struct format based on storagetype
            format_char = "H"  # Default to uint16
            if storagetype == "uint8":
                format_char = "B"
            elif storagetype == "int8":
                format_char = "b"
            elif storagetype == "float":
                format_char = "f"

            # Decode X and Y Axes, handling `swapxy="true"`
            if swap_axes:
                # Swap lengths and addresses
                elements_x, elements_y = elements_y, elements_x
                address_x, address_y = address_y, address_x
                scaling_x, scaling_y = scaling_y, scaling_x

            # Decode X Axis
            x_axis = []
            if address_x and elements_x:
                x_raw = struct.unpack_from(f"{endian}{elements_x}{format_char}", binary_data, address_x)
                x_axis = [apply_scaling(val, scaling_x) for val in x_raw]

            # Decode Y Axis
            y_axis = []
            if address_y and elements_y:
                y_raw = struct.unpack_from(f"{endian}{elements_y}{format_char}", binary_data, address_y)
                y_axis = [apply_scaling(val, scaling_y) for val in y_raw]

            # Decode Table Data
            table_data = []
            row_size = elements_x * struct.calcsize(format_char)
            for row_idx in range(elements_y):
                start = address + row_idx * row_size
                row_raw = struct.unpack_from(f"{endian}{elements_x}{format_char}", binary_data, start)
                row_scaled = [apply_scaling(val, table_scaling) for val in row_raw]
                table_data.append(row_scaled)

            # Handle `swapxy="true"`
            if swap_axes:
                # Transpose the table data after swapping
                table_data = list(map(list, zip(*table_data)))

            # Store decoded data
            decoded_data[mapping["name"]] = {
                "x_axis": x_axis,
                "y_axis": y_axis,
                "data": table_data,
            }

        except Exception as e:
            print(f"Error decoding table '{mapping['name']}': {e}")
            continue

    return decoded_data

def edit_bin(binary_file, mappings):
    """Edit the binary file by replacing an entire table including axes based on user input via the terminal."""
    with open(binary_file, "rb") as bin_file:
        binary_data = bytearray(bin_file.read())

    for mapping in mappings:
        name = mapping["name"]
        print(f"Editing table: {name}")
        address = mapping["address"]
        elements_x = mapping.get("elements_x", 0)
        elements_y = mapping.get("elements_y", 0)
        address_x = mapping.get("address_x")
        address_y = mapping.get("address_y")
        scaling = mapping.get("scaling")
        storagetype = scaling.get("storagetype") if scaling else "uint16"
        endian = ">" if scaling and scaling.get("endian") == "big" else "<"

        # Determine struct format based on storagetype
        format_char = "H"  # Default to uint16
        if storagetype == "uint8":
            format_char = "B"
        elif storagetype == "int8":
            format_char = "b"
        elif storagetype == "float":
            format_char = "f"

        # Show existing x, y, and table data
        if address_x and elements_x:
            x_axis = list(struct.unpack_from(f"{endian}{elements_x}{format_char}", binary_data, address_x))
            print(f"X Axis: {x_axis}")
        if address_y and elements_y:
            y_axis = list(struct.unpack_from(f"{endian}{elements_y}{format_char}", binary_data, address_y))
            print(f"Y Axis: {y_axis}")
        table_data = []
        for row in range(elements_y):
            start = address + row * elements_x * struct.calcsize(format_char)
            row_data = list(struct.unpack_from(f"{endian}{elements_x}{format_char}", binary_data, start))
            table_data.append(row_data)
            print(f"Row {row + 1}: {row_data}")

        # Prompt for full table replacement, including axes
        print(f"Enter new data for the table '{name}' including X and Y axes (row by row, space-separated):")
        new_x_axis = input("Enter new X Axis (space-separated): ")
        new_y_axis = input("Enter new Y Axis (space-separated): ")
        new_table_input = input("Paste the full table data here (rows space-separated):\n")

        try:
            # Parse X Axis
            new_x_axis = [float(x) for x in new_x_axis.split()]
            if len(new_x_axis) != elements_x:
                raise ValueError(f"X Axis length mismatch: expected {elements_x}, got {len(new_x_axis)}.")

            # Parse Y Axis
            new_y_axis = [float(y) for y in new_y_axis.split()]
            if len(new_y_axis) != elements_y:
                raise ValueError(f"Y Axis length mismatch: expected {elements_y}, got {len(new_y_axis)}.")

            # Parse Table Data
            new_table_data = []
            for line in new_table_input.strip().splitlines():
                row = [float(x) for x in line.split()]
                if len(row) != elements_x:
                    raise ValueError(f"Row length mismatch: expected {elements_x}, got {len(row)}.")
                new_table_data.append(row)
            if len(new_table_data) != elements_y:
                raise ValueError(f"Number of rows mismatch: expected {elements_y}, got {len(new_table_data)}.")

            # Write X Axis
            struct.pack_into(f"{endian}{len(new_x_axis)}{format_char}", binary_data, address_x, *new_x_axis)

            # Write Y Axis
            struct.pack_into(f"{endian}{len(new_y_axis)}{format_char}", binary_data, address_y, *new_y_axis)

            # Write Table Data
            for row_idx, row_data in enumerate(new_table_data):
                start = address + row_idx * elements_x * struct.calcsize(format_char)
                struct.pack_into(f"{endian}{len(row_data)}{format_char}", binary_data, start, *row_data)

        except ValueError as e:
            print(f"Error: {e}")
            continue

    # Save the modified binary file
    with open("modified_" + binary_file, "wb") as modified_bin_file:
        modified_bin_file.write(binary_data)

def main():
    # Select XML and binary files
    xml_file = select_file(".xml")
    if not xml_file:
        print("No XML file selected. Exiting.")
        return

    binary_file = select_file(".bin")
    if not binary_file:
        print("No binary file selected. Exiting.")
        return

    # Parse XML file
    mappings = parse_xml(xml_file)

    # Decode binary file
    decoded_data = decode_bin(binary_file, mappings)

    # Output decoded data
    print("\nDecoded data:")
    for key, value in decoded_data.items():
        print(f"\n{'=' * 50}")
        print(f"Table: {key}")
        print(f"{'-' * 50}")
        print(f"X Axis: {', '.join(map(str, value['x_axis']))}")
        print(f"Y Axis: {', '.join(map(str, value['y_axis']))}")

        # Handle empty data gracefully
        if not value["data"] or all(not row for row in value["data"]):
            print("Data: (empty table)")
            continue

        # Calculate min and max values for the color gradient
        flat_data = [val for row in value["data"] for val in row]
        min_val = min(flat_data)
        max_val = max(flat_data)

        print("Data:")
        for row in value["data"]:
            colored_row = "  ".join(apply_text_color(val, min_val, max_val) for val in row)
            print(colored_row)

    # Uncomment this block to enable editing functionality
    # edit_mode = input("\nDo you want to edit the binary file? (y/n): ").strip().lower() == "y"
    # if edit_mode:
    #     print("\nEditing binary file...")
    #     edit_bin(binary_file, mappings)
    #     print(f"Edits saved to 'modified_{binary_file}'")

if __name__ == "__main__":
    main()


   
