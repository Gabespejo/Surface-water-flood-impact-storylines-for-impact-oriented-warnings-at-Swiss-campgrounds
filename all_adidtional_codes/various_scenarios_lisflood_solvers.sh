#!/bin/bash

# ✅ Check input arguments
if [ "$#" -ne 5 ]; then
    echo "❌ Usage: $0 <case_study> <start_precip> <end_precip> <step_precip> <solver>"
    echo "Example: $0 Salavaux 25 80 5 acc"
    echo "Available solvers: acc, fv1-gpu, dg2, dg2-gpu"
    exit 1
fi

# ✅ Input parameters
case_study=$1
start_precip=$2
end_precip=$3
step_precip=$4
solver=$5

# ✅ Define LISFLOOD build and case folder paths
lisflood_build="/storage/homefs/ge24z347/LISFLOOD_FP_8_1/build"
case_folder="$lisflood_build/${case_study}"

# ✅ Change into case directory
cd "$case_folder" || { echo "❌ Error: Directory $case_folder not found!"; exit 1; }

# ✅ Set solver flags (for logging purposes only)
output_suffix="$solver"

case $solver in
    acc)
        solver_flag="-acceleration"
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
        echo "❌ Error: Unknown solver '$solver'. Choose from: acc, fv1, fv1-gpu, dg2, dg2-gpu"
        exit 1
        ;;
esac

# ✅ Function to update .par file with correct solver flags
modify_par_file() {
    input_file="$1"
    output_file="$2"
    solver="$3"
    new_dirroot="$4"

    cp "$input_file" "$output_file"

    # 🔧 Remove any existing solver flags (even commented)
    sed -i '/^[[:space:]]*#*[[:space:]]*acceleration[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*fv1[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*dg2[[:space:]]*$/d' "$output_file"
    sed -i '/^[[:space:]]*#*[[:space:]]*cuda[[:space:]]*$/d' "$output_file"

    # 🔁 Update dirroot to point to the correct output folder
    sed -i "s|^dirroot.*$|dirroot                   ${new_dirroot}|" "$output_file"

    # 🔧 Insert solver flags just before "sim_time"
    insert_line=$(grep -n "^sim_time" "$output_file" | cut -d: -f1)

    if [[ -n "$insert_line" ]]; then
        insert_line=$((insert_line - 1))
        case $solver in
            acc)
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
        echo "⚠️ Warning: 'sim_time' not found in $output_file. Solver flags not inserted."
    fi
}

# ✅ Loop through precipitation values and run LISFLOOD
for precip in $(seq $start_precip $step_precip $end_precip); do
    par_file="${case_study}_${precip}.par"
    temp_par_file="tmp_${par_file}"
    output_dir="${case_study}_${precip}_${output_suffix}"

    if [ -f "$par_file" ]; then
        echo "🚀 Running LISFLOOD for $par_file with solver '$solver' -> Output: $output_dir"
        mkdir -p "$output_dir"

        modify_par_file "$par_file" "$temp_par_file" "$solver" "$output_dir"

        # ✅ Use only the modified .par file, no extra CLI flags
        $lisflood_build/lisflood "$temp_par_file"

        echo "✅ Completed: $par_file ($solver)"
        rm -f "$temp_par_file"
    else
        echo "⚠️ Warning: $par_file not found, skipping..."
    fi
done

echo "🎯 All LISFLOOD simulations completed with solver: $solver"