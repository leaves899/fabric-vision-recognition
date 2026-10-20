# Run from E:/Internship_2026/织物识别工作区/fabric-vision-recognition.
# Choose a NEW output directory; preparation intentionally refuses an existing path.
$ErrorActionPreference = 'Stop'
$taskOut = 'experiments/yarn-graph-rerun-NEW'
$taskDemo = 'E:/Internship_2026/织物识别工作区/demo111/TextileDefectDetection_standalone_demo'
$taskFabric = 'E:/Internship_2026/织物识别工作区/FabricNET'
$taskAttachment = 'C:/Users/Administrator/AppData/Local/Temp/codex-clipboard-c1995be3-3bff-4985-87e2-d08c449b9ea4.jpg'
$taskBookPython = 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
$taskTfPython = "$taskDemo/.venv-author/Scripts/python.exe"
$taskPython = 'C:/Users/Administrator/miniconda3/python.exe'
# Process-scoped setting, avoiding a NumPy/Torch native-library conflict on this Windows installation.
$env:MKL_THREADING_LAYER = 'SEQUENTIAL'
& $taskBookPython -B -m benchmark.yarn_graph_experiments.prepare --out $taskOut --demo $taskDemo --fabric $taskFabric --attachment $taskAttachment
if ($LASTEXITCODE -ne 0) { throw 'Preparation failed' }
& $taskTfPython -B -m benchmark.yarn_graph_experiments.teacher --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Teacher inference failed' }
& $taskPython -B -m benchmark.yarn_graph_experiments.single_rgb --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Student run failed' }
& $taskPython -B -m benchmark.yarn_graph_experiments.connections --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Connection experiment failed' }
& $taskPython -B -m benchmark.yarn_graph_experiments.reconstruction --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Reconstruction failed' }
& $taskTfPython -B -m benchmark.yarn_graph_experiments.teacher_controls --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Teacher controls failed' }
& $taskPython -B -m pytest benchmark/yarn_graph_experiments/test_mechanics.py -q -p no:cacheprovider | Tee-Object -FilePath "$taskOut/mechanics_test.log"
if ($LASTEXITCODE -ne 0) { throw 'Mechanics tests failed' }
& $taskPython -B -m benchmark.yarn_graph_experiments.report --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Report generation failed' }
& $taskPython -B -m benchmark.yarn_graph_experiments.verify --out $taskOut
if ($LASTEXITCODE -ne 0) { throw 'Verification failed' }
