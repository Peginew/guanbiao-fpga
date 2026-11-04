import_device ph1_35p.db -package PH1P35MDG324 -speed 3
import_db {C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_landmark_s3_20261103/project/td_project/reader_landmark_s3_Runs/synth_20261103_181022_258861/reader_landmark_s3_gate.db}
puts {SYN_MACRO u_dashboard/mult2_syn_59}
set o [get_cells {u_dashboard/mult2_syn_59}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/mult4_syn_60}
set o [get_cells {u_dashboard/mult4_syn_60}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/ramread0_syn_23}
set o [get_cells {u_dashboard/ramread0_syn_23}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/ramread0_syn_29}
set o [get_cells {u_dashboard/ramread0_syn_29}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/ramread1_syn_23}
set o [get_cells {u_dashboard/ramread1_syn_23}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/ramread1_syn_29}
set o [get_cells {u_dashboard/ramread1_syn_29}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_dashboard/ramread1_syn_35}
set o [get_cells {u_dashboard/ramread1_syn_35}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_hdmi_mixer/u_anlogic_logo_rom/u_index0_syn_1}
set o [get_cells {u_hdmi_mixer/u_anlogic_logo_rom/u_index0_syn_1}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_hdmi_mixer/u_anlogic_logo_rom/u_index1_syn_1}
set o [get_cells {u_hdmi_mixer/u_anlogic_logo_rom/u_index1_syn_1}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO u_hdmi_mixer/u_anlogic_logo_rom/u_palette_syn_1}
set o [get_cells {u_hdmi_mixer/u_anlogic_logo_rom/u_palette_syn_1}]
if {[llength $o]!=1} {error {SYN_MACRO_NOT_UNIQUE}}
report_cells $o -attributes -connection
puts {SYN_MACRO_READONLY_INVENTORY_COMPLETE}
exit 0
