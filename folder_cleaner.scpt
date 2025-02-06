#!/usr/bin/osascript

tell application "Photos"
    try
        if not (exists folder "02_What") then
            make new folder named "02_What"
        end if
        
        set albumList to {}
        repeat with anAlbum in albums
            if not (exists parent folder of anAlbum) then
                set albumName to name of anAlbum
                if albumName contains ":" then
                    if (first character of albumName) is in {"A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"} then
                        copy anAlbum to end of albumList
                    end if
                end if
            end if
        end repeat
        
        set albumCount to count of albumList
        if albumCount is 0 then
            return "No albums found with category prefixes"
        end if
        
        repeat with theAlbum in albumList
            set albumName to name of theAlbum
            set category to text 1 thru ((offset of ":" in albumName) - 1) of albumName
            
            tell folder "02_What"
                if not (exists folder category) then
                    make new folder named category
                end if
            end tell
            
            tell folder category of folder "02_What"
                make new album named albumName
            end tell
            
            set newAlbum to album albumName of folder category of folder "02_What"
            repeat with anItem in media items of theAlbum
                add anItem to newAlbum
            end repeat
            
            delete theAlbum
        end repeat
        
        return "Processed " & albumCount & " albums"
        
    on error errMsg number errorNumber
        return "Error " & errorNumber & ": " & errMsg
    end try
end tell