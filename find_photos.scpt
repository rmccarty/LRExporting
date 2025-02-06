-- First make sure Photos isn't already running
tell application "Photos" to quit
delay 2

tell application "Photos"
    activate
    delay 5
    
    -- Wait for Photos to be ready
    repeat until application "Photos" is running
        delay 1
    end repeat
    
    -- Additional delay to ensure library is loaded
    delay 10
    
    -- Make sure we can access the library
    try
        repeat 5 times
            try
                -- Try to get the name of the library first
                set libName to name of container of every media item
                log "Successfully connected to Photos library"
                exit repeat
            on error errMsg
                log "Waiting for Photos library to be ready..."
                delay 5
            end try
        end repeat
    end try
    
    -- Additional safety delay
    delay 5
    
    log "Starting photo search..."
    
    try
        -- Get all containers (albums, etc)
        set lib to default library
        
        -- Counter for limiting results
        set photoCount to 0
        set photoLimit to 10
        
        -- Get all photos from library
        repeat with thePhoto in (media items of lib)
            try
                set photoTitle to title of thePhoto
                if photoTitle is not missing value and photoTitle contains ":" then
                    set photoId to id of thePhoto
                    log "Found photo:"
                    log "Title: " & photoTitle
                    log "ID: " & photoId
                    log "----------------------------------------"
                    
                    -- Increment counter and check limit
                    set photoCount to photoCount + 1
                    if photoCount ≥ photoLimit then
                        exit repeat
                    end if
                end if
            on error errMsg
                -- Skip photos that can't be accessed
                log "Error with photo: " & errMsg
                delay 1
            end try
        end repeat
        
        if photoCount = 0 then
            log "No matching photos found"
        else
            log "Found " & photoCount & " matching photos"
        end if
        
    on error errMsg
        log "Error accessing photos: " & errMsg
    end try
end tell