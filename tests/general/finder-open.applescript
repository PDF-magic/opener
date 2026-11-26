-- Finder's Open verb follows the user's existing PDF association.
-- The document path is supplied as an argument, never interpolated into source.
on run argv
    if (count of argv) is not 1 then error "Provide exactly one PDF path."
    set requestedPDF to POSIX file (item 1 of argv)
    tell application id "com.apple.finder"
        open requestedPDF
    end tell
end run
