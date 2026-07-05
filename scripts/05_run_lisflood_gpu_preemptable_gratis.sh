#!/bin/bash
#SBATCH --account=gratis
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --partition=gpu
#SBATCH --qos=job_gpu_preemptable
#SBATCH --time=02:00:00

#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=gabriela.espejogutierrez@unibe.ch

#SBATCH --output=/storage/homefs/ge24z347/LISFLOOD_FP_8_1/scripts/logs/%x_%j.out
#SBATCH --error=/storage/homefs/ge24z347/LISFLOOD_FP_8_1/scripts/logs/%x_%j.err

# 1) Start clean
echo "Purging environment modules..."
module purge

# 2) Load modules
echo "Loading modules..."
module load foss || { echo "Failed to load foss"; exit 1; }
module load CMake || { echo "Failed to load CMake"; exit 1; }
module load netCDF/4.9.2-gompi-2023a || { echo "Failed to load netCDF"; exit 1; }
module load CUDA || { echo "Failed to load CUDA"; exit 1; }

# 3) Show module versions
echo "nvcc: $(which nvcc)  --  $(nvcc --version | head -n1)"
module list 2>&1

# 4) Check GPU access
echo "Available GPUs:"
nvidia-smi

# 5) Activate conda environment
echo "Activating conda environment env_py311..."
source /storage/homefs/ge24z347/mambaforge/etc/profile.d/conda.sh
conda activate env_py311 || { echo "Failed to activate environment"; exit 1; }

# 6) Start GPU monitoring safely
GPU_LOG="/storage/homefs/ge24z347/gpu_usage.log"
echo "Starting GPU monitoring in background..."
monitor_gpu_usage() {
    while true; do
        nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,memory.used,memory.free,memory.total \
        --format=csv,noheader >> "$GPU_LOG"
        sleep 60
    done
}
sleep 5
monitor_gpu_usage &
MONITOR_PID=$!
trap "echo 'Killing GPU monitoring...'; kill $MONITOR_PID" EXIT

# 7) Run LISFLOOD using reusable solver script
echo "Running LISFLOOD via various_scenarios_lisflood_solvers.sh..."

# Default values if not provided
BASENAME=${1:-Gordevio_2m}
START=${2:-10}
END=${3:-110}
STEP=${4:-5}
SOLVER=${5:-fv1-gpu}

echo "Running: $BASENAME from $START to $END with step $STEP using solver $SOLVER"

bash /storage/homefs/ge24z347/Campgrounds/scripts/various_scenarios_lisflood_solvers.sh "$BASENAME" "$START" "$END" "$STEP" "$SOLVER"

echo "✅ LISFLOOD batch simulation completed."
