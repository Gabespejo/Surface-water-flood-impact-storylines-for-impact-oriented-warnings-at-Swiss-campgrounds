#!/bin/bash
#SBATCH --account=gratis
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --partition=gpu
#SBATCH --qos=job_gpu_preemptable
#SBATCH --time=6:00:00
#SBATCH --output=/storage/homefs/ge24z347/LISFLOOD_FP_8_1/scripts/logs/%x_%j.out
#SBATCH --error=/storage/homefs/ge24z347/LISFLOOD_FP_8_1/scripts/logs/%x_%j.err

# SLURM email notifications (BEGIN/END/FAIL/TIME_LIMIT)
#SBATCH --mail-user=gabriela.espejogutierrez@unibe.ch
#SBATCH --mail-type=BEGIN,END,FAIL,TIME_LIMIT

MAIL_USER="gabriela.espejogutierrez@unibe.ch"

# -------------------- 1) Start clean --------------------
echo " Purging environment modules..."
module purge

# -------------------- 2) Load modules -------------------
echo " Loading modules..."
module load foss || { echo " Failed to load foss"; exit 1; }
module load CMake || { echo " Failed to load CMake"; exit 1; }
module load netCDF/4.9.2-gompi-2023a || { echo " Failed to load netCDF"; exit 1; }
module load CUDA || { echo " Failed to load CUDA"; exit 1; }

# -------------------- 3) Show versions ------------------
echo " Python: $(which python)  --  $(python --version)"
echo " nvcc: $(which nvcc)  --  $(nvcc --version | head -n1)"

echo " Loaded modules:"
module list 2>&1

# -------------------- 4) Check GPU ----------------------
echo "  Available GPUs:"
nvidia-smi

echo " Environment check completed successfully."

# -------------------- Input args ------------------------
if [ "$#" -ne 5 ]; then
    echo "Usage: $0 <case_study> <start_precip> <end_precip> <step_precip> <solver>"
    echo "Example: $0 Morges_2m_v2 5 75 10 acc-gpu"
    echo "Available solvers: acc, acc-gpu, fv1, fv1-gpu, dg2, dg2-gpu"
    exit 1
fi

case_study=$1
start_precip=$2
end_precip=$3
step_precip=$4
solver=$5

# -------------------- Paths -----------------------------
lisflood_build="/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build"
case_folder="$lisflood_build/${case_study}"

cd "$case_folder" || { echo " Error: Directory $case_folder not found!"; exit 1; }

GPU_LOG="/storage/homefs/ge24z347/gpu_usage_${case_study}_${SLURM_JOB_ID}.log"
STATS_LOG="/storage/homefs/ge24z347/LISFLOOD_FP_8_1/scripts/logs/stats_${case_study}_${SLURM_JOB_ID}.log"

echo "[INFO] GPU log   : ${GPU_LOG}"
echo "[INFO] STATS log : ${STATS_LOG}"

# -------------------- Solver flags (logging only) -------
output_suffix="$solver"

case $solver in
    acc)
        solver_flag="-acceleration"
        ;;
    acc-gpu)
        solver_flag="-acceleration -cuda"
        ;;
    fv1)
        solver_flag="-fv1"
        ;;
    fv1-gpu)
        solver_flag="-fv1 -cuda"
        ;;
    dg2)
        solver_flag="-dg2"
        ;;
    dg2-gpu)
        solver_flag="-dg2 -cuda"
        ;;
    *)
        echo " Error: Unknown solver '$solver'. Choose from: acc, acc-gpu, fv1, fv1-gpu, dg2, dg2-gpu"
        exit 1
        ;;
esac

# -------------------- GPU monitoring --------------------
echo "[INFO] Starting GPU monitoring to ${GPU_LOG} ..."
monitor_gpu_usage() {
    while true; do
        nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,utilization.memory,\
memory.used,memory.free,memory.total \
        --format=csv,noheader >> "${GPU_LOG}"
        sleep 60
    done
}

sleep 5
monitor_gpu_usage &
MONITOR_PID=$!
trap "echo '[INFO] Stopping GPU monitor'; kill ${MONITOR_PID} 2>/dev/null || true" EXIT

# -------------------- Disk/time BEFORE ------------------
START_TIME=$SECONDS

DU_BEFORE_KB=$(du -s "${case_folder}" | awk '{print $1}')
DU_BEFORE_MB=$((DU_BEFORE_KB / 1024))
echo "[INFO] Disk BEFORE: ${DU_BEFORE_MB} MB in ${case_folder}"
echo "DISK_BEFORE_MB=${DU_BEFORE_MB}" > "${STATS_LOG}"

runs_total=0
runs_done=0
runs_skipped=0

# -------------------- Modify .par file ------------------
modify_par_file() {
    input_file="$1"
    output_file="$2"
    solver="$3"
    new_dirroot="$4"

    cp "$input_file" "$output_file"

    # Remove existing solver flags (even commented)
    sed -i '/^[[:space:]]*#*[[:space:]]*acceleration[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*fv1[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*dg2[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*cuda[[:space:]]*$/d' "$output_file"

    # Update dirroot to correct output folder
    sed -i "s|^dirroot.*$|dirroot                   ${new_dirroot}|" "$output_file"

    # Insert solver flags just before sim_time
    insert_line=$(grep -n "^sim_time" "$output_file" | cut -d: -f1)

    if [[ -n "$insert_line" ]]; then
        insert_line=$((insert_line - 1))
        case $solver in
            acc)
                sed -i "${insert_line}i acceleration" "$output_file"
                ;;
            acc-gpu)
                sed -i "${insert_line}i cuda" "$output_file"
                sed -i "${insert_line}i acceleration" "$output_file"
                ;;
            fv1)
                sed -i "${insert_line}i fv1" "$output_file"
                ;;
            fv1-gpu)
                sed -i "${insert_line}i cuda" "$output_file"
                sed -i "${insert_line}i fv1" "$output_file"
                ;;
            dg2)
                sed -i "${insert_line}i dg2" "$output_file"
                ;;
            dg2-gpu)
                sed -i "${insert_line}i cuda" "$output_file"
                sed -i "${insert_line}i dg2" "$output_file"
                ;;
        esac
    else
        echo " Warning: 'sim_time' not found in $output_file. Solver flags not inserted."
    fi
}

# -------------------- Main loop -------------------------
for precip in $(seq $start_precip $step_precip $end_precip); do
    par_file="${case_study}_${precip}.par"
    temp_par_file="tmp_${par_file}"
    output_dir="${case_study}_${precip}_${output_suffix}"

    runs_total=$((runs_total + 1))

    if [ -f "$par_file" ]; then
        echo " Running LISFLOOD for $par_file with solver '$solver' -> Output: $output_dir"
        mkdir -p "$output_dir"

        modify_par_file "$par_file" "$temp_par_file" "$solver" "$output_dir"

        # Debug check (optional; comment out later)
        echo "[DEBUG] Key lines in ${temp_par_file}:"
        grep -nE "^(acceleration|fv1|dg2|cuda|sim_time|dirroot)" "$temp_par_file" | head -n 30

        # Run LISFLOOD using only the modified .par file
        $lisflood_build/lisflood "$temp_par_file"
        exit_code=$?

        if [ $exit_code -eq 0 ]; then
            echo " Completed: $par_file ($solver) with EXIT_CODE=0"
            runs_done=$((runs_done + 1))
        else
            echo " LISFLOOD failed for $par_file ($solver) with EXIT_CODE=${exit_code}"
        fi

        rm -f "$temp_par_file"
    else
        echo " Warning: $par_file not found, skipping..."
        runs_skipped=$((runs_skipped + 1))
    fi
done

echo " All LISFLOOD simulations completed with solver: $solver"
echo "Total: ${runs_total}, Done: ${runs_done}, Skipped (missing par): ${runs_skipped}"

# -------------------- Disk/time AFTER -------------------
END_TIME=$SECONDS
RUNTIME=$((END_TIME - START_TIME))
RUNTIME_MIN=$((RUNTIME / 60))

DU_AFTER_KB=$(du -s "${case_folder}" | awk '{print $1}')
DU_AFTER_MB=$((DU_AFTER_KB / 1024))
DISK_DELTA_MB=$((DU_AFTER_MB - DU_BEFORE_MB))

echo "[INFO] Total runtime: ${RUNTIME} seconds (~${RUNTIME_MIN} minutes)"
echo "[INFO] Disk AFTER:  ${DU_AFTER_MB} MB in ${case_folder}"
echo "[INFO] Disk change: ${DISK_DELTA_MB} MB"

{
  echo "RUNTIME_SECONDS=${RUNTIME}"
  echo "RUNTIME_MINUTES=${RUNTIME_MIN}"
  echo "DISK_AFTER_MB=${DU_AFTER_MB}"
  echo "DISK_DELTA_MB=${DISK_DELTA_MB}"
  echo "RUNS_TOTAL=${runs_total}"
  echo "RUNS_DONE=${runs_done}"
  echo "RUNS_SKIPPED=${runs_skipped}"
} >> "${STATS_LOG}"

# -------------------- Email report ----------------------
REPORT="/storage/homefs/ge24z347/jobreport_${case_study}_${SLURM_JOB_ID}.txt"

{
  echo "Job report for LISFLOOD multi-scenario run"
  echo "=========================================="
  echo
  echo "User:        ${USER}"
  echo "Job ID:      ${SLURM_JOB_ID}"
  echo "Job name:    ${SLURM_JOB_NAME}"
  echo "Case study:  ${case_study}"
  echo "Case folder: ${case_folder}"
  echo
  echo "Scenarios:"
  echo "  Start:     ${start_precip}"
  echo "  End:       ${end_precip}"
  echo "  Step:      ${step_precip}"
  echo "  Solver:    ${solver}"
  echo
  echo "Runs:"
  echo "  Total:     ${runs_total}"
  echo "  Completed: ${runs_done}"
  echo "  Skipped:   ${runs_skipped} (missing .par)"
  echo
  echo "Runtime:"
  echo "  Seconds:   ${RUNTIME}"
  echo "  Minutes:   ${RUNTIME_MIN}"
  echo
  echo "Disk usage:"
  echo "  BEFORE:    ${DU_BEFORE_MB} MB"
  echo "  AFTER:     ${DU_AFTER_MB} MB"
  echo "  DELTA:     ${DISK_DELTA_MB} MB"
  echo
  echo "Stats log:   ${STATS_LOG}"
  echo "GPU log:     ${GPU_LOG}"
  echo
  echo "=== STATS LOG CONTENT ==="
  if [ -f "${STATS_LOG}" ]; then
    cat "${STATS_LOG}"
  else
    echo "(Stats log not found.)"
  fi
  echo
  echo "=== Last 20 lines of GPU usage log ==="
  if [ -f "${GPU_LOG}" ]; then
    tail -n 20 "${GPU_LOG}"
  else
    echo "(GPU usage log not found.)"
  fi
} > "${REPORT}"

if command -v mail >/dev/null 2>&1; then
    mail -s "LISFLOOD multi-scenario job report: ${case_study} (Job ${SLURM_JOB_ID})" \
         "${MAIL_USER}" < "${REPORT}"
    echo "[INFO] Sent detailed job report email to ${MAIL_USER}"
else
    echo "[WARN] 'mail' command not available; could not send email report."
fi

