# Windows에서 scheduler.py를 "재부팅해도 자동 시작 + 죽으면 자동 재시작"되는
# 작업 스케줄러(Task Scheduler) 작업으로 등록하는 스크립트.
#
# 사용법(README "무인 운영을 위한 3가지 추가 설정" 참고):
#   1) 아래 $ProjectDir, $PythonExe 변수를 실제 경로로 바꾼다.
#   2) PowerShell을 "관리자 권한으로 실행"한 뒤:
#        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
#        .\deploy\windows\register_scheduler_task.ps1
#   3) 확인: 작업 스케줄러 앱 → "작업 스케줄러 라이브러리"에서
#      "NaverBlogScheduler" 작업 확인 (재부팅 시 자동 시작, 실패 시 1분
#      간격으로 재시작하도록 등록된다)
#
# 절전 방지: 이 작업이 실행되는 동안 컴퓨터가 잠들면 스케줄러도 같이
# 멈춘다. 아래 powercfg 명령도 같이 실행해 절전을 꺼둔다(전원이 연결돼
# 있을 때만 — 배터리 구동 노트북이면 "standby-timeout-dc"도 0으로 바꾼다).
#   powercfg /change standby-timeout-ac 0
#   powercfg /change hibernate-timeout-ac 0

$ProjectDir = "<여기를-바꾸세요: 예: C:\naver_blog_automation>"
$PythonExe  = "<여기를-바꾸세요: 예: C:\naver_blog_automation\.venv\Scripts\python.exe>"
$Account    = "<계정이름>"
$TaskName   = "NaverBlogScheduler"

$action = New-ScheduledTaskAction -Execute $PythonExe `
    -Argument "scheduler.py --account $Account" `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBattery `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)   # 무제한 실행(스케줄러는 계속 돎)

# SYSTEM 계정으로 등록하면 로그인 없이도 재부팅 즉시 시작된다.
# 화면을 띄워서(headless=False) 확인하고 싶다면 -User "$env:USERNAME"과
# -LogonType Interactive로 바꾸고 자동 로그인 설정이 필요하다.
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force

Write-Host "작업 '$TaskName'을 등록했습니다. 재부팅 시 자동 시작되고, 죽으면 1분 뒤 재시작합니다."

# 절전 방지(전원 연결 상태 기준 — 노트북이면 -dc 버전도 같이 실행 권장)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Write-Host "절전 모드(AC 전원 기준)를 껐습니다."
