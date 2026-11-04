if {[catch {
import_device ph1_35p.db -package PH1P35MDG324 -speed 3
open_project reader_landmark_s3.prj
commit_param -step design
elaborate -top design_top_wrapper
set rx [get_ports {I_rover_uart_rx}]
set tx [get_ports {O_rover_uart_tx}]
if {[llength $rx] != 1 || [llength $tx] != 1} {error {MERGED_UART_PORTS_MISSING}}
puts {MERGED_PROJECT_SOURCE_ELABORATION_COMPLETE_NOT_IMPLEMENTATION}
close_project
} err]} {puts stderr "MERGED_PROJECT_SOURCE_CHECK_FAILED: $err";exit 1}
exit 0
