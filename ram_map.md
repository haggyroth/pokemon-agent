
# Pokémon 3rd Generation/Pokémon FireRed and LeafGreen/RAM map
From Data Crystal

Ram Maps sources:

[(pokecommunity) POKEMON FIRERED RAM OFFSET LIST"](http://www.pokecommunity.com/showthread.php?t=342546)

[(pokecommunity) DavidJCobb's (WIP) firered RAM map"](http://www.pokecommunity.com/showthread.php?t=342546)

Note: _For anyone unfamiliar with the syntax, the brackets means "use the value at this address", so in this case you'd first load the address at ...008 and then add that address and use it to get what you want_

## Quick List

Map

0x02036DFC Current Map Header

  
Player

X = \[0x03005008\] + 0x000 
Y = \[0x03005008\] + 0x002
Map Number = \[0x03005008\] + 0x005

Money

Key = \[0x0300500C\] + 0x0F20 
Money\_Hidden = \[0x03005008\] + 0x0218 (possibly + 0x0290)

Money = Money XOR Key

## Standard

### EWRAM

0x02002D40        ?    Start of data that apparently controls 
                the colors of the pixels inside of the 
                current box (menu, msgbox, etc.).
0x02007370         8b    Name in name entry during new game intro
0x020204B4        12b    Dialog box 1
0x020204C0        12b    Dialog box 2
0x020204CC        12b    Dialog box 3
0x020204D8        12b    Dialog box 4
0x020204E4        12b    Dialog box 5
0x020204F0        12b    Dialog box 6
0x020204FC        12b    Dialog box 7
0x02020508        12b    Dialog box 8
0x02020514        12b    Dialog box 9
0x02020520        12b    Dialog box 10
0x0202052C        12b    Dialog box 11
0x02020538        12b    Dialog box 12
0x02020544        12b    Dialog box 13
0x02020550        12b    Dialog box 14
0x0202055C        12b    Dialog box 15
0x02020568        12b    Dialog box 16
0x02020574        12b    Dialog box 17
0x02020580        12b    Dialog box 18
0x0202058C        12b    Dialog box 19
0x02020598        12b    Dialog box 20
0x020205A4        12b    Dialog box 21
0x020205B0        12b    Dialog box 22
0x020205BC        12b    Dialog box 23
0x020205C8        12b    Dialog box 24
0x020205D4        12b    Dialog box 25
0x020205E0        12b    Dialog box 26
0x020205EC        12b    Dialog box 27
0x020205F8        12b    Dialog box 28
0x02020604        12b    Dialog box 29
0x02020610        12b    Dialog box 30
0x0202061C        12b    Dialog box 31
0x02020628        12b    Dialog box 32
0x02021CD0        32b    String buffer 0
0x02021CF0        20b    String buffer 1
0x02021D04        20b    String buffer 2
0x02021D18        ?    String to be displayed in a message box
0x02022B4B        1b    Flags for current battle?
0x02022B4C        4b    Flags for current battle? Set to 0x8 by repeattrainerbattle.
0x02023E8A        1b    Repeattrainerbattle: Unknown. Loaded if battle type is 9.
0x02024029        1b    Repeattrainerbattle: Unknown. Loaded if battle type is 9.
0x0202402C        100b    Enemy Pokemon 1
0x02024090        100b    Enemy Pokemon 2
0x020240F4        100b    Enemy Pokemon 3
0x02024158        100b    Enemy Pokemon 4
0x020241BC        100b    Enemy Pokemon 5
0x02024220        100b    Enemy Pokemon 6
0x02024284         100b    Party Pokemon 1
0x020242E8         100b    Party Pokemon 2
0x0202434C         100b    Party Pokemon 3
0x020243B0         100b    Party Pokemon 4
0x02024414         100b    Party Pokemon 5
0x02024478         100b    Party Pokemon 6
0x020245CC        8b    Player name
0x02028F78        8b    Rival name
0x02031DB4        1b    Previous map bank number
0x02031DB5        1b    Previous map number
0x02031DB6        1b    Warp through which the player entered the current map?
0x02031DB7        1b    Padding?
0x02031DB8        2b    X where player entered previous map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DBA        2b    Y where player entered previous map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DBC        1b    Current map bank number
0x02031DBD        1b    Current map number
0x02031DBE        1b    Warp through which the player entered the current map?
0x02031DBF        1b    Padding?
0x02031DC0        2b    X where player entered current map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DC2        2b    Y where player entered current map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DC3        1b    Padding?
0x02031DC4        1b    Current2 map bank number
0x02031DC5        1b    Current2 map number
0x02031DC6        1b    Warp through which the player entered the current2 map?
0x02031DC7        1b    Padding?
0x02031DC8        2b    X where player entered current2 map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DCA        2b    Y where player entered current2 map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DCC        1b    Current3 map bank number
0x02031DCD        1b    Current3 map number
0x02031DCE        1b    Warp through which the player entered the current3 map?
0x02031DCF        1b    Padding?
0x02031DD0        2b    X where player entered current3 map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DD2        2b    Y where player entered current3 map, or 0xFFFF if unused.
                (Only seems to be used when the warp was a door.)
0x02031DD4        3b?    Warping: Unknown. Always set to 01 01 00 when "warp" and 
                "warpmuted" finish, but not when "warp3" finishes. While 
                walking into a door warp, the second byte is 02.
0x02031DD7        1b    Warping: Unknown. Seems to always be 0x03.
0x02031DD8        1b    Warping: Unknown. If non-zero, "warp" fails to play a 
                sound.
0x02031DDA       2b?    Unknown. Changes every time you warp.
0x02036E38        36b    OW 00 (player)
0x02036E5C        36b    OW 01
0x02036E80        36b    OW 02
0x02036EA4        36b    OW 03
0x02036EC8        36b    OW 04
0x02036EEC        36b    OW 05
0x02036F10        36b    OW 06
0x02036F34        36b    OW 07
0x02036F58        36b    OW 08
0x02036F7C        36b    OW 09
0x02036FA0        36b    OW 10
0x02036FC4        36b    OW 11
0x02036FE8        36b    OW 12
0x0203700C        36b    OW 13
0x02037030        36b    OW 14
0x02037054        36b    OW 15
0x02037078        1b    Three least-significant bits control player speed.
0x02037079        1b    Something to do with switching into biking OW?
0x0203707A        1b    Is a D-pad button pressed (player attempting to move)?
0x0203707B        1b    Is the player actually moving?
0x0203707C        1b    Unknown.
0x0203707D        1b    Person number to be controlled by the D-pad.
0x0203707E        1b    If set to 0x01, all OW movement is locked. (lockall flag?)
0x020370B8        2b    Script variable 0x8000
0x020370BA        2b    Script variable 0x8001
0x020370BC        2b    Script variable 0x8002
0x020370BE        2b    Script variable 0x8003
0x020370C0        2b    Script variable 0x8004
0x020370C2        2b    Script variable 0x8005
0x020370C4        2b    Script variable 0x8006
0x020370C6        2b    Script variable 0x8007
0x020370C8        2b    Script variable 0x8008
0x020370CA        2b    Script variable 0x8009
0x020370CC        2b    Script variable 0x800A
0x020370CE        2b    Script variable 0x800B
0x020370D0        2b    Script variable 0x800D // there is no var 0x800C?
0x020370D2        2b    Script variable 0x800E // overwritten by "trainerbattle"?
0x020370D4        2b    Script variable 0x800F
0x020386AC        2b    Trainerbattle: Battle type.
0x020386AE        2b    Trainerbattle: Trainer flag.
0x020386B0        2b    Trainerbattle: Argument 3.
                    Some battle types save it into var 0x800E.
0x020386B2        2b    Unknown.
0x020386B4        4b    Trainerbattle: Arg4 (types 1, 2, 4, 6, 7, 8) or null (others).
0x020386B8        4b    Trainerbattle: A4 (0, 3, 5), A5 (1, 2, 4, 6, 7, 8, 9), or null.
0x020386BC        4b    Trainerbattle: Argument 5 (type 9) or null (others).
0x020386C0        4b    Trainerbattle: Argument 6 (types 6, 8) or null (others).
0x020386C4        4b    Trainerbattle: Offset of next script command byte.
0x020386C8        4b    Trainerbattle: A6 (types 1, 2), A7 (types 6, 8), or null.
0x020386CC        2b    Trainerbattle: Unknown.
0x0203AAA8        4b    Unknown. Written to by the "setbyte" command.
0x0203ADE6        1b    Cursor position
0x0203ADFA        1b    Unknown.
                    If equal to 0x2, "warp" fails to play a sound.
                    If lower than 0x04, "setworldmapflag" fails to set 
                        the specified flag.
                    If equal to 1, trainerbattle types 5 and 7 will 
                    clear this byte and then some sections of RAM.
0x0203ADFC        4b    Unknown. A pointer used by trainerbattle types 5 and 7.
0x0203AE04        4b?    Unknown. Cleared by "trainerbattle" (types 5, 7) if the byte 
                at 0x0203ADFA is 0x01.
0x0203AE08        4b?    Unknown. Used and cleared by "trainerbattle" (types 5, 7) 
                if the byte at 0x0203ADFA is 0x01.
0x0203AE8C        4b?    Unknown. Cleared by "trainerbattle" (types 5, 7) if the byte 
                at 0x0203ADFA is 0x01.

0x0203AE98        ?    Unknown.
0x0203AF98        ?    Unknown. A pointer used by trainerbattle types 5 and 7.
0x0203B01E        2b    Unknown. Read by a reused ASM routine in script commands' 
                code.
0x0203B0EE        1b    Help: Player's opened it before? Y / N, 0x00 / 0x01.
0x0203B1A0        14291b    Help: unknown. // to 0x0203E973
0x0203E973        2050b    Help: unknown. Cleared only when opening help for the 1st 
                time. // to 0x0203F175
0x0203F176        1b    Help: start of GUI state data.
0x0203F194        1b    Help: number of menu options.
0x0203F195        1b    Help: Unknown.
0x0203F196        1b    Help: number of menu options visible on-screen.
0x0203F199        1b    Help: Unknown. Apparently 0x04 for top-level menu or 0x15 
                for submenus.
0x0203F19C        1b    Help: scroll position in a menu.
0x0203F19D        1b    Help: cursor position in a menu (relative to scroll).
0x0203F19E        1b    Help: unknown. Apparently 0x00 for top-level menu, 0x03 
                for submenus, and 0x06 for static pages.
0x0203F1AC        ?b    Help: start of menu data. String pointer (not aligned), 
                followed by menu item number. List is terminated with 
                0xFEFFFFFF
0x0203E000        4096b    Unused RAM found by JPAN (is used by D/N patch)
0x0203F3C0        1856b    RAM used in JPAN's Hacked Engine.

### IWRAM

0x03000EA8        1b    Unknown. Set by (defunct?) "choosecontestpkmn" command, and 
                also set to 0x1 by "repeattrainerbattle".
0x03000EB0        74b    Script engine RAM
0x03000F9C        1b    0x01 if the screen is fading, 0x00 otherwise.
0x03000FC0        4b    Music for the current map (truncated to 2b when read)
0x03000FC4        1b    Warping: Unknown.
0x03005000        4b    Current PRNG seed
0x03005008        4b    Pointer to a DMA-protected save block (map data)
0x0300500C        4b    Pointer to a DMA-protected save block (personal data)
0x03005010        4b    Pointer to a DMA-protected save block (box data)
0x03005074        1b    Trainerbattle: number of the OW we are battling, or 0x10 if 
                invalid. This offset is used by special 13A, which in turn 
                is called by some of the scripts (yes, scripts) that 
                trainerbattle calls.
0x03005E88        1b?    Unknown. Cleared by "trainerbattle" (types 5, 7) if the byte 
                at 0x0203ADFA is 0x01.
0x03007324        2b    Warping: Unknown. Related to the fade timer.
0x03007326        2b    Warping: Unknown. Related to the fade timer.
0x03007328        2b    Warping: Timer used for fades. Duration varies with type 
               of map being entered.
0x03007CF0        1b    Position of cursor in selection of Rival's name during new game intro (US 1.1)

## DMA (Dynamic, exact address constantly changes)

\[0x03005008\] + 0x0000    2b    Camera X-position
\[0x03005008\] + 0x0002    2b    Camera Y-position
\[0x03005008\] + 0x0004    1b    Current map.
\[0x03005008\] + 0x0005    1b    Current map bank.

\[0x0300500C\] + 0x0000   8b    Character name including terminator, padded to end with 0xFFs
\[0x0300500C\] + 0x0008    1b    Gender (00/01 m/f)
\[0x0300500C\] + 0x0009    1b    Unknown
\[0x0300500C\] + 0x000A    2b    Trainer ID
\[0x0300500C\] + 0x000C    2b    Secret ID (halfword)
\[0x0300500C\] + 0x000E    2b    Playtime (hours)
\[0x0300500C\] + 0x0010    1b    Playtime (minutes)
\[0x0300500C\] + 0x0011    1b    Playtime (seconds)
\[0x0300500C\] + 0x0012    1b    Playtime (frames)
\[0x0300500C\] + 0x0014    2b    Options // this and above thanks to hackmew's asm tut pt. 1
\[0x0300500C\] + 0x001A    1b    If 0xDA, then National Dex is enabled.
\[0x0300500C\] + 0x0028   52bytes Flags of Pokemon caught
\[0x0300500C\] + 0x005c   52bytes Flags of Pokemon seen
\[0x0300500C\] + 0x0F20    4b    Unknown (encryption key for hidden vars)
\[0x0300500C\] + 0x0F24        End (byte after)

Collapse

_Internal Data for [Pokémon 3rd Generation/Pokémon FireRed and LeafGreen](/wiki/Pok%C3%A9mon_3rd_Generation/Pok%C3%A9mon_FireRed_and_LeafGreen "Pokémon 3rd Generation/Pokémon FireRed and LeafGreen")_

[ROM map](/wiki/Pok%C3%A9mon_3rd_Generation/Pok%C3%A9mon_FireRed_and_LeafGreen/ROM_map "Pokémon 3rd Generation/Pokémon FireRed and LeafGreen/ROM map") • RAM map • [Text table](/wiki/Pok%C3%A9mon_3rd_Generation/Pok%C3%A9mon_FireRed_and_LeafGreen/TBL "Pokémon 3rd Generation/Pokémon FireRed and LeafGreen/TBL") • [Notes](/w/index.php?title=Pok%C3%A9mon_3rd_Generation/Pok%C3%A9mon_FireRed_and_LeafGreen/Notes&action=edit&redlink=1 "Pokémon 3rd Generation/Pokémon FireRed and LeafGreen/Notes (page does not exist)") • [Tutorials](/wiki/Pok%C3%A9mon_3rd_Generation/Pok%C3%A9mon_FireRed_and_LeafGreen/Tutorials "Pokémon 3rd Generation/Pokémon FireRed and LeafGreen/Tutorials")

Retrieved from "[https://datacrystal.tcrf.net/w/index.php?title=Pokémon\_3rd\_Generation/Pokémon\_FireRed\_and\_LeafGreen/RAM\_map&oldid=65582](https://datacrystal.tcrf.net/w/index.php?title=Pokémon_3rd_Generation/Pokémon_FireRed_and_LeafGreen/RAM_map&oldid=65582)"

[Category](/wiki/Special:Categories "Special:Categories"):

-   [RAM maps](/wiki/Category:RAM_maps "Category:RAM maps")