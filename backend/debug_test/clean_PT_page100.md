# Extracted from: ptug+.pdf (Page 100)

Chapter 4: Managing Performance and Capacity
Distributed Multi-Scenario Analysis

|Life cycle states|Col2|Col3|
|---|---|---|
|Set up the host options with the<br>`set_host_options` command|Set up the host options with the<br>`set_host_options` command|Set up the host options with the<br>`set_host_options` command|
||||
|Start the remote host processes using the<br>`start_hosts` command|Start the remote host processes using the<br>`start_hosts` command|Start the remote host processes using the<br>`start_hosts` command|
||||
|Remote processes start up and form<br>connections back to the master|Remote processes start up and form<br>connections back to the master|Remote processes start up and form<br>connections back to the master|
||||
|Remote processes accepted online by the<br>`start_hosts` command|Remote processes accepted online by the<br>`start_hosts` command|Remote processes accepted online by the<br>`start_hosts` command|
||||
|Remote processes transition to the<br>available state and can accept tasks to<br>process|Remote processes transition to the<br>available state and can accept tasks to<br>process|Remote processes transition to the<br>available state and can accept tasks to<br>process|
|Remote processes transition to the<br>available state and can accept tasks to<br>process|Remote processes transition to the<br>available state and can accept tasks to<br>process|Remote processes transition<br>to the terminate state|
|Remote processes transition to the<br>available state and can accept tasks to<br>process|||



**DMSA Virtual Workers**



**[Feedback](mailto:docfeedback1@synopsys.com?subject=Documentation%20Feedback%20on%20PrimeTime%C2%AE%20User%20Guide&body=Version%20information:%20W-2024.09,%20September%202024%0A%0A(Enter%20your%20comments%20for%20Technical%20Publications%20here.%20Please%20include%20the%20topic%20heading%20and%20PDF%20page%20number%20to%20make%20it%20easier%20to%20locate%20the%20information.)%0A%0A)**



When the number of scenarios exceeds the number of available hosts, at least two
scenarios must be assigned to run on a host. If multiple commands are executed in those
scenarios, the tool must perform save and restore operations to swap designs in and out
of memory for executing each command, which can consume significant runtime and
network resources.

In this situation, you can avoid the additional runtime and delay by setting a “load factor” in
the `set_host_options` command:
```
   pt_shell> set_host_options -load_factor 2 ...
```

The default load factor is 1, which disables the feature. Setting a value of 2 reduces save
and restore operations at the cost of more memory.

The feature works by creating virtual workers in memory that can each handle one
scenario. A setting of 2 doubles the number of workers by creating one virtual worker in
memory for each real worker. If the real and virtual workers can accept all the scenarios at
the same time, there is no need for save and restore operations.

The following `set_host_options` command examples demonstrate this feature. The
`-submit_command` option shows the syntax for submitting jobs to an LSF farm with a
specific memory allocation; use the appropriate syntax for your installation.


PrimeTime® User Guide 101
W-2024.09


