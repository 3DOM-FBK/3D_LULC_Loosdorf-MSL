import os
import glob
import argparse
import numpy as np
import laspy
import meshio


def laz2ply(pc_path):
    """
    Convert a single LAZ file to PLY.
    """

    las = laspy.read(pc_path)

    # XYZ coordinates
    XYZ = np.stack((las.x, las.y, las.z), axis=1)

    # Handle NormalizedZ safely (assumed always present in your case)
    point_data = {
        "Green":las["Green"], 
        "NIR":las["NIR"], 
        "NormalizedZ": las["NormalizedZ"], 
        "GT_L1": las["GT_L1"],
        "GT_L2": las["GT_L2"] 
    }

    # Create mesh
    mesh = meshio.Mesh(
        points=XYZ,
        point_data=point_data,
        cells=[]
    )

    output_path = os.path.splitext(pc_path)[0] + ".ply"

    meshio.write(output_path, mesh)

    print(f"✓ Saved: {output_path}")


def convert_folder(folder_path, recursive=False):

    if not os.path.isdir(folder_path):
        print(f"Error: Folder does not exist:\n{folder_path}")
        return

    if recursive:
        laz_files = glob.glob(os.path.join(folder_path, "**", "*.laz"), recursive=True)
    else:
        laz_files = glob.glob(os.path.join(folder_path, "*.laz"))

    if not laz_files:
        print("No .laz files found.")
        return

    print(f"Found {len(laz_files)} LAZ files.\n")

    success = 0
    failed = 0

    for laz_file in laz_files:
        print(f"Processing: {laz_file}")

        try:
            laz2ply(laz_file)
            success += 1
        except Exception as e:
            failed += 1
            print(f"✗ Failed: {laz_file}")
            print(f"  Error: {e}")

    print("\n==============================")
    print("Done!")
    print(f"Successful: {success}")
    print(f"Failed: {failed}")
    print("==============================")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Convert LAZ files to PLY")

    parser.add_argument("folder", help="Folder containing LAZ files")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="Search subfolders")

    args = parser.parse_args()

    convert_folder(args.folder, args.recursive)
