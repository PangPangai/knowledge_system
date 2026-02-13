# Extracted from: fusion compiler application options and attributes 24.09.sp3.pdf (Page 102)

**[Feedback](mailto:docfeedback1@synopsys.com?subject=Documentation%20Feedback%20on%20Fusion%20Compiler%20Application%20Options%20and%20Attributes&body=Version%20information:%20W-2024.09-SP3,%20January%202025%0A%0A(Enter%20your%20comments%20for%20Technical%20Publications%20here.%20Please%20include%20the%20topic%20heading%20and%20PDF%20page%20number%20to%20make%20it%20easier%20to%20locate%20the%20information.)%0A%0A)**

# g
### **Fusion Compiler Application Options**


Thtu dietmno� dnueitbnu �hn u<<ateu�tio i<�tiou ut<<ii�nd by �hn Ftutio Cim<tani �iia.

##### **3**

###### **3dic.common.die_heights**

S<netftnu �hn hntph�u if �hn dtnu.

**Data Types**

u�itop <uti atu�

**Default** Em<�y atu�

**Description**

S<netftnu �hn hntph�u if �hn dtnu to u u�itop <uti atu�. Eueh <uti tu eim<itodnd by u ftaa
atbiuiy dnutpo oumn uod t�u hntph� _uatn to �hn tot� if tm. Eueh hntph� euo hu_n u utopan
_uatn in<inuno�top �hn hntph� if �hn dtn ii mta�t<an _uatnu in<inuno�top �hn mta�tan_na
hntph�; �hn mta�tan_na hntph� dnoi�nu �hn hntph�u if �hn dtn an_nau fiim �hn bi��im �i �hn �i<
iidniay. Miini_ni, tf ion tunu �hn mta�tan_na hntph�, �hn hntph� if �hn dtn tu �hn utm if �hn
_uatnu if �hn mta�tan_na hntph�.

**Examples**

Thn fiaaiwtop nxum<an uhiwu hiw �i u<netfy �hn hntph�u if �hn dtnu:
```
   prompt> set_app_options -name 3dic.common.die_heights -value { \\
   { si_interposer.ndm:si_interposer 100 } \\
   { leon3mp_chip.ndm:leon3mp_chip 20 } \\
   { mem.ndm:mem 20 } }
```

Thn fiaaiwtop nxum<an uhiwu hiw �i u<netfy �hn mta�tan_na hntph� if �hn dtn:
```
   prompt> set_app_options -name 3dic.common.die_heights -value { \\
   { si_interposer.ndm:si_interposer { 50 50 } } \\
   { leon3mp_chip.ndm:leon3mp_chip 20 } \\
   { mem.ndm:mem 20 } }

```

Ftutio Cim<tani A<<ateu�tio O<�tiou uod A��itbt�nu g03
W-2024.09-SP3


