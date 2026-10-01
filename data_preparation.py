import os
import argparse
from pathlib import Path

import numpy as np
import torch
from plyfile import PlyData


# ============================================================
# CONFIGURATION
# ============================================================

BLOCK_SIZE = 50.0
STRIDE = 50.0
PADDING = 0.01
MIN_POINTS = 4096
GLOBAL_MAX_H = 50.0


# ============================================================
# READ PLY
# ============================================================

def read_ply(filepath):
    ply = PlyData.read(str(filepath))
    v = ply["vertex"]

    def field(names, default=None):
        for name in names:
            try:
                return np.asarray(v[name], dtype=np.float64)
            except (ValueError, KeyError):
                pass
        return default

    # Required XYZ
    x = np.asarray(v["x"], dtype=np.float64)
    y = np.asarray(v["y"], dtype=np.float64)
    z = np.asarray(v["z"], dtype=np.float64)

    # Green
    green=field(
        [
            "Green",
        ],
        np.zeros(len(x), dtype=np.float64),
    )

    # NIR
    nir=field(
        [
            "NIR",
        ],
        np.zeros(len(x), dtype=np.float64),
    )

    # Normalized Z
    normz = field(
        [
            "NormalizedZ"
        ]
    )

    if normz is None:
        normz = z - z.min()


    # Ground truth
    gt = field(
        [
            "GT_L2" # change it to "GT_L1" for the LULC-L1
        ],
        np.full(len(x), -1, dtype=np.float64),
    )

    has_gt = np.any(gt >= 0)

    pc = np.column_stack(
        [
            x,
            y,
            z,
            green,
            nir,
            normz,
            gt,
        ]
    )

    return pc, has_gt


# ============================================================
# CREATE BLOCKS
# ============================================================

def create_blocks(
    pc,
    output_dir,
    filename_prefix="upload",
    progress_callback=None,
):
    os.makedirs(output_dir, exist_ok=True)

    # Original global XYZ coordinates
    xyz_global = pc[:, :3].copy()

    # Shift point cloud so minimum coordinate is zero
    min_coord = np.min(pc[:, :3], axis=0)

    work = pc.copy()
    work[:, :3] -= min_coord

    xyz = work[:, :3]

    # Features:
    #   column 3 = green
    #   column 4 = nir
    #   column 5 = normz
    feats = work[:, [3, 4, 5]].copy()

    # Normalize height
    feats[:, 1] = np.clip(
        feats[:, 1] / GLOBAL_MAX_H,
        0,
        1,
    )

    points = np.hstack(
        [
            xyz,
            feats,
        ]
    )

    labels = work[:, -1]

    # Spatial extent
    coord_min = points[:, :3].min(axis=0)
    coord_max = points[:, :3].max(axis=0)

    # Number of blocks in X
    gx = max(
        1,
        int(
            np.ceil(
                (coord_max[0] - coord_min[0] - BLOCK_SIZE)
                / STRIDE
            ) + 1
        ),
    )

    # Number of blocks in Y
    gy = max(
        1,
        int(
            np.ceil(
                (coord_max[1] - coord_min[1] - BLOCK_SIZE)
                / STRIDE
            ) + 1
        ),
    )

    files = []
    info = {}
    count = 0

    total = gx * gy

    for iy in range(gy):
        for ix in range(gx):

            # ------------------------------------------------
            # X range
            # ------------------------------------------------

            sx = coord_min[0] + ix * STRIDE

            ex = min(
                sx + BLOCK_SIZE,
                coord_max[0],
            )

            sx = ex - BLOCK_SIZE

            # ------------------------------------------------
            # Y range
            # ------------------------------------------------

            sy = coord_min[1] + iy * STRIDE

            ey = min(
                sy + BLOCK_SIZE,
                coord_max[1],
            )

            sy = ey - BLOCK_SIZE

            # ------------------------------------------------
            # Find points inside block
            # ------------------------------------------------

            idx = np.where(
                (points[:, 0] >= sx - PADDING)
                & (points[:, 0] <= ex + PADDING)
                & (points[:, 1] >= sy - PADDING)
                & (points[:, 1] <= ey + PADDING)
            )[0]

            # Skip blocks with too few points
            if idx.size < MIN_POINTS:
                continue

            # Randomize point order
            np.random.shuffle(idx)

            batch = points[idx].copy()
            n = len(idx)

            # ------------------------------------------------
            # Normalized XYZ
            # ------------------------------------------------

            normxyz = np.zeros(
                (n, 3),
                dtype=np.float64,
            )

            for k in range(3):
                if coord_max[k] != 0:
                    normxyz[:, k] = (
                        batch[:, k] / coord_max[k]
                    )
                else:
                    normxyz[:, k] = 0

            # ------------------------------------------------
            # Center X/Y around block center
            # ------------------------------------------------

            batch[:, 0] -= (
                sx + BLOCK_SIZE / 2
            )

            batch[:, 1] -= (
                sy + BLOCK_SIZE / 2
            )

            # Add normalized XYZ
            batch = np.hstack(
                [
                    batch,
                    normxyz,
                ]
            )

            # ------------------------------------------------
            # Create Pytorch dictionary
            # ------------------------------------------------

            d = {
                "coord": batch[:, :3].astype(
                    np.float32
                ),

                "global_coord": xyz_global[idx].astype(
                    np.float64
                ),

                "color": batch[:, 3:6].astype(
                    np.float32
                ),

                "semantic_gt": labels[idx, None].astype(
                    np.int64
                ),
            }

            # ------------------------------------------------
            # Save block
            # ------------------------------------------------

            path = os.path.join(
                output_dir,
                f"{filename_prefix}_Block_{count}.pth",
            )

            torch.save(d, path)

            files.append(path)

            info[count] = {
                "point_idxs": idx.copy(),
                "n_points": n,
            }

            count += 1

            # ------------------------------------------------
            # Progress
            # ------------------------------------------------

            if progress_callback:
                progress_callback(
                    (iy * gx + ix + 1) / total,
                    f"Creating block "
                    f"{iy * gx + ix + 1}/{total}",
                )

    return {
        "block_files": files,
        "block_info": info,
        "n_blocks": count,
        "min_coord": min_coord,
        "xyz_global": xyz_global,
        "total_points": len(pc),
        "coord_min": coord_min,
        "coord_max": coord_max,
    }


# ============================================================
# PREPROCESS ONE PLY
# ============================================================

def preprocess(
    filepath,
    output_dir,
    progress_callback=None,
):
    filepath = Path(filepath)
    output_dir = Path(output_dir)

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if progress_callback:
        progress_callback(
            0.05,
            "Reading PLY file...",
        )

    # Read PLY
    pc, has_gt = read_ply(filepath)

    original_count = len(pc)

    # --------------------------------------------------------
    # Remove invalid rows
    # --------------------------------------------------------

    valid = np.isfinite(pc).all(axis=1)

    # Mapping to original input rows
    original_row_index = np.arange(
        original_count,
        dtype=np.int64,
    )

    if not valid.all():

        invalid_count = np.sum(~valid)

        print(
            f"  Removing {invalid_count:,} invalid points."
        )

        pc = pc[valid]

        original_row_index = (
            original_row_index[valid]
        )

    if len(pc) == 0:
        raise ValueError(
            "No valid points remain after removing "
            "NaN/Inf values."
        )

    # --------------------------------------------------------
    # Block progress callback
    # --------------------------------------------------------

    def cb(p, msg):

        if progress_callback:
            progress_callback(
                0.25 + 0.70 * p,
                msg,
            )

    # --------------------------------------------------------
    # Create blocks
    # --------------------------------------------------------

    result = create_blocks(
        pc=pc,
        output_dir=str(output_dir),
        filename_prefix=filepath.stem,
        progress_callback=cb,
    )

    if result["n_blocks"] == 0:
        raise ValueError(
            "No valid 50m blocks with at least "
            "4096 points were created."
        )

    if progress_callback:
        progress_callback(
            1.0,
            "Preprocessing complete.",
        )

    return {
        **result,
        "blocks_dir": str(output_dir),
        "original_pc": pc,
        "original_row_index": original_row_index,
        "original_point_count": original_count,
        "processed_point_count": len(pc),
        "has_gt": has_gt,
        "filepath": str(filepath),
        "filename": filepath.name,
    }


# ============================================================
# PROCESS ALL PLY FILES
# ============================================================

def preprocess_folder(
    input_dir,
    output_dir,
):
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)

    # --------------------------------------------------------
    # Check input
    # --------------------------------------------------------

    if not input_dir.exists():
        raise FileNotFoundError(
            f"Input directory does not exist:\n{input_dir}"
        )

    if not input_dir.is_dir():
        raise NotADirectoryError(
            f"Input path is not a directory:\n{input_dir}"
        )

    # --------------------------------------------------------
    # Create output
    # --------------------------------------------------------

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Find PLY files
    # --------------------------------------------------------

    ply_files = sorted(
        input_dir.glob("*.ply")
    )

    if not ply_files:

        print(
            f"No .ply files found in:\n{input_dir}"
        )

        return

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("PLY BATCH PREPROCESSING")
    print("=" * 70)

    print(f"Input folder : {input_dir}")
    print(f"Output folder: {output_dir}")
    print(f"PLY files    : {len(ply_files)}")

    print("=" * 70)

    successful = 0
    failed = 0

    failed_files = []

    # --------------------------------------------------------
    # Process each PLY
    # --------------------------------------------------------

    for file_number, ply_file in enumerate(
        ply_files,
        start=1,
    ):

        print()
        print("=" * 70)

        print(
            f"[{file_number}/{len(ply_files)}] "
            f"{ply_file.name}"
        )

        print("=" * 70)

        # Each PLY gets its own folder
        file_output_dir = (
            output_dir / ply_file.stem
        )

        try:

            def progress_callback(
                progress,
                message,
            ):

                print(
                    f"  [{progress * 100:6.2f}%] "
                    f"{message}"
                )

            result = preprocess(
                filepath=ply_file,
                output_dir=file_output_dir,
                progress_callback=progress_callback,
            )

            successful += 1

            print()
            print(
                f"SUCCESS: {ply_file.name}"
            )

            print(
                f"  Points processed : "
                f"{result['processed_point_count']:,}"
            )

            print(
                f"  Blocks created   : "
                f"{result['n_blocks']:,}"
            )

            print(
                f"  Output directory : "
                f"{file_output_dir}"
            )

        except Exception as e:

            failed += 1
            failed_files.append(ply_file.name)

            print()
            print(
                f"FAILED: {ply_file.name}"
            )

            print(
                f"  Error: {e}"
            )

    # --------------------------------------------------------
    # Final summary
    # --------------------------------------------------------

    print()
    print()
    print("=" * 70)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 70)

    print(
        f"Total files : {len(ply_files)}"
    )

    print(
        f"Successful  : {successful}"
    )

    print(
        f"Failed      : {failed}"
    )

    print(
        f"Output      : {output_dir}"
    )

    print("=" * 70)

    if failed_files:

        print()
        print("Failed files:")

        for filename in failed_files:
            print(f"  - {filename}")

    print()


# ============================================================
# COMMAND LINE INTERFACE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Preprocess all PLY files in a folder "
            "into 50m point-cloud blocks."
        )
    )

    parser.add_argument(
        "input_dir",
        type=str,
        help="Path to folder containing PLY files",
    )

    parser.add_argument(
        "output_dir",
        type=str,
        help="Path where processed blocks will be saved",
    )

    args = parser.parse_args()

    preprocess_folder(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
