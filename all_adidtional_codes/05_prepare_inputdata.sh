#!/bin/bash

# --- INPUT ARGUMENTS ---
BASENAME=$1         # e.g., Liestal_2m
LOCATION_ID=$2      # e.g., 2
WORK_NAME=$3        # e.g., LIESTAL
DEM_FOLDER_NAME=$4  # e.g., LIESTAL_DEM_2M
START=${5:-10}
END=${6:-110}
STEP=${7:-5}

# --- CHECK ---
if [ -z "$BASENAME" ] || [ -z "$LOCATION_ID" ] || [ -z "$WORK_NAME" ] || [ -z "$DEM_FOLDER_NAME" ]; then
  echo "❌ Usage: ./prepare_all_inputs_local.sh BASENAME LOCATION_ID WORK_NAME DEM_FOLDER_NAME [START] [END] [STEP]"
  exit 1
fi

# --- ACTIVATE ENVIRONMENT ---
echo "🔧 Activating env_py311..."
source /storage/homefs/ge24z347/mambaforge/etc/profile.d/conda.sh
conda activate env_py311 || { echo "❌ Failed to activate env_py311"; exit 1; }

# --- PATHS ---
DEM_FOLDER="/rs_scratch/users/ge24z347/${DEM_FOLDER_NAME}"
WORK_FOLDER="${DEM_FOLDER}/${WORK_NAME}"
BUILD_FOLDER="/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build/${BASENAME}"
CATCHMENT_CSV="/rs_scratch/users/ge24z347/Data_forprocess/catchment_location.csv"
AREAL_GPKG="/rs_scratch/users/ge24z347/Data_forprocess/Arealstatistik_processing/arealstatistik.gpkg"
OUTPUT_PREFIX="${BUILD_FOLDER}/${BASENAME}"
OUTPUT_DEM="${OUTPUT_PREFIX}.dem"
OUTPUT_N="${OUTPUT_PREFIX}.n"
PRECIP_DEM="${OUTPUT_PREFIX}.dem"

mkdir -p "$BUILD_FOLDER"

# --- STEP 1: DEM ---
echo "🔹 [1/4] DEM..."
python /storage/homefs/ge24z347/Campgrounds/scripts/01_prepare_dem_camp.py \
  --location-csv "$CATCHMENT_CSV" \
  --dem-folder "$DEM_FOLDER" \
  --work-folder "$WORK_FOLDER" \
  --output-dem "$OUTPUT_DEM" \
  --location-id "$LOCATION_ID" \
  --width 2000 \
  --height 2000 \
  --resolution 2.0

# --- STEP 2: Manning .n ---
echo "🔹 [2/4] Manning..."
python /storage/homefs/ge24z347/Campgrounds/scripts/02_prepare_manning_values_camp.py \
  --areal-gpkg "$AREAL_GPKG" \
  --code-field LC_27 \
  --work-folder "$BUILD_FOLDER" \
  --output-n "$OUTPUT_N" \
  --res-2m 2.0

# --- STEP 3: NetCDF rainfall ---
echo "🌧️  [3/4] Rainfall NetCDF..."
python /storage/homefs/ge24z347/Campgrounds/scripts/03_prepare_netcdfiles_camp.py \
  --dem-file "$PRECIP_DEM" \
  --start "$START" \
  --end "$END" \
  --step "$STEP"

# --- STEP 4: .par / .stage / renamed files ---
echo "📦 [4/4] LISFLOOD scenario files..."
python /storage/homefs/ge24z347/Campgrounds/scripts/04_prepare_command_lisflood.py \
  --build-dir "$BUILD_FOLDER" \
  --base-name "$BASENAME" \
  --location-id "$LOCATION_ID" \
  --start "$START" \
  --end "$END" \
  --step "$STEP"

echo "✅ Input preparation completed for $BASENAME"