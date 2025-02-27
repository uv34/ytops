import struct
import pyogg

def get_granule_positions(file_path):
    """
    Extracts the granule positions of all Ogg pages in the file.
    Returns a list of granule positions.
    """
    granule_positions = []
    with open(file_path, 'rb') as f:
        offset = 0
        while True:
            header = f.read(27)
            if len(header) < 27:
                break
            if not header.startswith(b"OggS"):
                break

            # Extract granule position (bytes 6–13)
            granule_pos_bytes = header[6:14]
            granule_pos = struct.unpack('<Q', granule_pos_bytes)[0]  # Little-endian unsigned 64-bit

            granule_positions.append(granule_pos)

            # Move to the next page
            page_segments = header[26]
            segment_table = f.read(page_segments)
            page_size = 27 + page_segments + sum(segment_table)
            offset += page_size
            f.seek(offset)

    return granule_positions


def get_sample_rate(file_path):
    """
    Uses PyOgg to extract the sample rate of the Ogg Vorbis file.
    """
    vorbis_file = pyogg.VorbisFile(file_path)
    return vorbis_file.frequency


def get_time_until_page(file_path, target_page_index):
    """
    Returns the total time (in seconds) from the start of the file
    up to the specified page (target_page_index).

    If target_page_index is 0, the output is 0 seconds.
    If target_page_index exceeds the total number of pages, returns total duration.
    """
    granule_positions = get_granule_positions(file_path)
    sample_rate = get_sample_rate(file_path)

    total_pages = len(granule_positions)

    if target_page_index <= 0:
        return 0.0  # No time passed before the first page

    if target_page_index >= total_pages:
        # If the target page exceeds the total pages, return the total duration
        total_samples = granule_positions[-1]
        total_time = total_samples / sample_rate
        return total_time

    # The granule position of the target page represents the total samples up to that page
    samples_up_to_page = granule_positions[target_page_index]
    time_up_to_page = samples_up_to_page / sample_rate

    return time_up_to_page


def build_page_index(file_path):
    """
    Returns a list of byte offsets for each OggS page in the file:
      page_offsets[i] = byte_offset_of_page_i
    """
    page_offsets = []
    with open(file_path, 'rb') as f:
        offset = 0
        while True:
            header = f.read(27)
            if len(header) < 27:
                break
            if not header.startswith(b"OggS"):
                break

            page_segments = header[26]
            segment_table = f.read(page_segments)
            if len(segment_table) < page_segments:
                break

            page_size = 27 + page_segments + sum(segment_table)

            page_offsets.append(offset)

            offset += page_size
            f.seek(offset, 0)

    return page_offsets


def build_time_index(file_path, total_pages):
    """
    builds a list that contains the time of each page where the index is the page and the time is the element
    """
    granule_positions = get_granule_positions(file_path)
    sample_rate = get_sample_rate(file_path)

    total_pages = len(granule_positions)

    page_times = []
    for target_page_index in range(0, total_pages):
        if target_page_index <= 0:
            page_times.append(0.0)

        if target_page_index >= total_pages:
            total_samples = granule_positions[-1]
            total_time = total_samples / sample_rate
            page_times.append(total_time)

        samples_up_to_page = granule_positions[target_page_index]
        time_up_to_page = samples_up_to_page / sample_rate
        page_times.append(time_up_to_page)

    print(page_times)
    return page_times


def get_ogg_duration(file_path):
    """
    Returns the duration (in seconds) of an Ogg Vorbis file using PyOgg.
    """
    vorbis_file = pyogg.VorbisFile(file_path)
    data = vorbis_file.buffer
    sample_rate = vorbis_file.frequency
    channels = vorbis_file.channels

    total_bytes = len(data)
    bytes_per_sample = 2  # 16-bit
    samples_per_frame = channels
    num_frames = total_bytes // (bytes_per_sample * samples_per_frame)
    duration = num_frames / float(sample_rate)
    return duration


def extract_header_data_and_last_page(file_path, chunk_size=8192):
    """
    Extract all Ogg pages at the start that contain the 3 Vorbis headers
    (packets 0x01, 0x03, 0x05).

    Returns (header_data, last_header_page_index)

    'header_data' is the raw concatenation of the Ogg pages for those headers.
    'last_header_page_index' is the highest page index that contains
    any part of the 3rd header packet, so we know where the real audio begins.

     parse packets within each page:
      - If packet type 0x01 (ID), 0x03 (comment), or 0x05 (setup),
        mark them found.
      - Once all 3 are found, the next packet is likely audio.
      - notes the Ogg page index it ended on.
    """
    needed = {0x01, 0x03, 0x05}
    found = set()

    header_data = bytearray()
    last_header_page_idx = 0

    page_index = 0
    with open(file_path, "rb") as f:
        buffer = bytearray()
        done = False
        while not done:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            buffer.extend(chunk)

            while True:
                if b"OggS" not in buffer:
                    break
                idx = buffer.index(b"OggS")
                if idx > 0:
                    buffer = buffer[idx:]

                if len(buffer) < 27:
                    break
                segs = buffer[26]
                header_size = 27 + segs
                if len(buffer) < header_size:
                    break

                seg_table = buffer[27:header_size]
                page_size = 27 + len(seg_table) + sum(seg_table)
                if len(buffer) < page_size:
                    break

                page = buffer[:page_size]
                buffer = buffer[page_size:]

                # Parse the packets in this page
                # to detect if they contain ID(0x01), Comment(0x03), or Setup(0x05).
                data_start = header_size
                data_end = page_size
                packet_data = bytearray()

                for seg_len in seg_table:
                    if data_start + seg_len > data_end:
                        break
                    packet_data.extend(page[data_start:(data_start + seg_len)])
                    data_start += seg_len

                    if seg_len < 255:
                        # packet boundary
                        if packet_data:
                            # check first byte
                            first_byte = packet_data[0]
                            if first_byte in needed:
                                found.add(first_byte)
                        packet_data = bytearray()

                # Append this entire page to header_data
                header_data.extend(page)
                # If we found at least one header packet here,
                # update last_header_page_idx
                if len(found) > 0:
                    last_header_page_idx = page_index

                # If we've found all 3, we can stop
                if found == needed:
                    done = True

                page_index += 1
    return bytes(header_data), last_header_page_idx


def count_ogg_pages(filename):
    """
    Count the number of pages in an Ogg file.

    Parameters:
        filename (str): Path to the Ogg file.

    Returns:
        int: The number of pages in the file.
    """
    count = 0
    try:
        with open(filename, "rb") as f:
            while True:
                # Read the capture pattern (should be "OggS")
                capture = f.read(4)
                if len(capture) < 4:
                    break  # End of file
                if capture != b'OggS':
                    # The file is not a valid Ogg file or has become unsynchronized.
                    break

                count += 1

                # Read the rest of the fixed header (23 bytes, making total header 27 bytes)
                header = f.read(23)
                if len(header) < 23:
                    break

                # The last byte of the header is the number of segments
                page_segments = header[-1]

                # Read the segment table (one byte per segment)
                segment_table = f.read(page_segments)
                if len(segment_table) < page_segments:
                    break

                # The sum of the segment table gives the total size of the page data in bytes.
                page_data_size = sum(segment_table)

                # Skip the page data.
                f.seek(page_data_size, 1)
    except Exception as e:
        print("Error reading file:", e)
        return 0

    return count

