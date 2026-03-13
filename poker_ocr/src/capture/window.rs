use anyhow::{Result, anyhow};
use core_foundation::base::TCFType;
use core_foundation::dictionary::CFDictionaryRef;
use core_foundation::string::CFString;
use core_graphics::display::*;
use serde::Serialize;

use super::WindowInfo;

/// Info returned by --list-windows
#[derive(Debug, Clone, Serialize)]
pub struct WindowListEntry {
    pub window_id: u32,
    pub name: String,
    pub owner: String,
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

/// Get info for a specific window by ID.
pub fn get_window_info(window_id: u32) -> Result<WindowInfo> {
    let windows = list_all_windows()?;
    windows
        .into_iter()
        .find(|w| w.window_id == window_id)
        .map(|w| WindowInfo {
            window_id: w.window_id,
            name: w.name,
            x_pt: w.x,
            y_pt: w.y,
            w_pt: w.width,
            h_pt: w.height,
        })
        .ok_or_else(|| anyhow!("Window {} not found", window_id))
}

/// List all GGPoker table windows.
pub fn list_ggpoker_windows() -> Result<Vec<WindowListEntry>> {
    let all = list_all_windows()?;
    let poker_keywords = ["Blinds", "Spin", "Gold", "Rush", "Cash", "Hold", "Omaha", "NL", "PLO"];
    let exclude_keywords = ["Highlight", "Cashier", "Settings", "Options"];

    Ok(all
        .into_iter()
        .filter(|w| {
            let is_gg = w.owner == "GGnet" || w.owner.contains("GG");
            if !is_gg {
                return false;
            }
            let has_keyword = poker_keywords.iter().any(|kw| w.name.contains(kw));
            let excluded = exclude_keywords.iter().any(|kw| w.name.contains(kw));
            has_keyword && !excluded && w.width > 200 && w.height > 200
        })
        .collect())
}

// Core Foundation C types we need
#[allow(non_camel_case_types)]
type CFArrayRef = *const std::ffi::c_void;
#[allow(non_camel_case_types)]
type CFTypeRef = *const std::ffi::c_void;

extern "C" {
    fn CFArrayGetCount(array: CFArrayRef) -> isize;
    fn CFArrayGetValueAtIndex(array: CFArrayRef, idx: isize) -> CFTypeRef;
    fn CFDictionaryGetValue(dict: CFDictionaryRef, key: CFTypeRef) -> CFTypeRef;
    fn CFGetTypeID(cf: CFTypeRef) -> usize;
    fn CFStringGetTypeID() -> usize;
    fn CFNumberGetTypeID() -> usize;
    fn CFDictionaryGetTypeID() -> usize;
    fn CFStringGetCString(
        string: CFTypeRef,
        buffer: *mut u8,
        buffer_size: isize,
        encoding: u32,
    ) -> bool;
    fn CFNumberGetValue(number: CFTypeRef, the_type: isize, value_ptr: *mut std::ffi::c_void) -> bool;
    fn CFRelease(cf: CFTypeRef);
}

const K_CF_STRING_ENCODING_UTF8: u32 = 0x08000100;
const K_CF_NUMBER_SINT64_TYPE: isize = 4;

/// List all windows on the system via CGWindowListCopyWindowInfo.
fn list_all_windows() -> Result<Vec<WindowListEntry>> {
    let window_list: CFArrayRef = unsafe {
        CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements,
            kCGNullWindowID,
        ) as CFArrayRef
    };

    if window_list.is_null() {
        return Ok(Vec::new());
    }

    let count = unsafe { CFArrayGetCount(window_list) };
    let mut results = Vec::new();

    for i in 0..count {
        let dict_ref = unsafe { CFArrayGetValueAtIndex(window_list, i) };
        if dict_ref.is_null() {
            continue;
        }

        let window_id = cf_dict_get_i64(dict_ref, "kCGWindowNumber").unwrap_or(0) as u32;
        let name = cf_dict_get_string(dict_ref, "kCGWindowName").unwrap_or_default();
        let owner = cf_dict_get_string(dict_ref, "kCGWindowOwnerName").unwrap_or_default();

        // Get bounds from sub-dictionary
        let (x, y, w, h) = cf_dict_get_bounds(dict_ref).unwrap_or((0, 0, 0, 0));

        if window_id > 0 && w > 0 && h > 0 {
            results.push(WindowListEntry {
                window_id,
                name,
                owner,
                x,
                y,
                width: w,
                height: h,
            });
        }
    }

    unsafe { CFRelease(window_list) };

    Ok(results)
}

fn cf_dict_get_string(dict: CFTypeRef, key: &str) -> Option<String> {
    let cf_key = CFString::new(key);
    let value = unsafe { CFDictionaryGetValue(dict as CFDictionaryRef, cf_key.as_CFTypeRef() as CFTypeRef) };
    if value.is_null() {
        return None;
    }

    // Verify it's a string type
    let type_id = unsafe { CFGetTypeID(value) };
    let string_type_id = unsafe { CFStringGetTypeID() };
    if type_id != string_type_id {
        return None;
    }

    let mut buf = [0u8; 1024];
    let ok = unsafe {
        CFStringGetCString(
            value,
            buf.as_mut_ptr(),
            buf.len() as isize,
            K_CF_STRING_ENCODING_UTF8,
        )
    };
    if ok {
        let s = std::ffi::CStr::from_bytes_until_nul(&buf)
            .ok()?
            .to_str()
            .ok()?
            .to_string();
        Some(s)
    } else {
        None
    }
}

fn cf_dict_get_i64(dict: CFTypeRef, key: &str) -> Option<i64> {
    let cf_key = CFString::new(key);
    let value = unsafe { CFDictionaryGetValue(dict as CFDictionaryRef, cf_key.as_CFTypeRef() as CFTypeRef) };
    if value.is_null() {
        return None;
    }

    let type_id = unsafe { CFGetTypeID(value) };
    let number_type_id = unsafe { CFNumberGetTypeID() };
    if type_id != number_type_id {
        return None;
    }

    let mut result: i64 = 0;
    let ok = unsafe {
        CFNumberGetValue(
            value,
            K_CF_NUMBER_SINT64_TYPE,
            &mut result as *mut i64 as *mut std::ffi::c_void,
        )
    };
    if ok { Some(result) } else { None }
}

fn cf_dict_get_bounds(dict: CFTypeRef) -> Option<(i32, i32, i32, i32)> {
    let cf_key = CFString::new("kCGWindowBounds");
    let bounds_dict = unsafe { CFDictionaryGetValue(dict as CFDictionaryRef, cf_key.as_CFTypeRef() as CFTypeRef) };
    if bounds_dict.is_null() {
        return None;
    }

    // Verify it's a dictionary
    let type_id = unsafe { CFGetTypeID(bounds_dict) };
    let dict_type_id = unsafe { CFDictionaryGetTypeID() };
    if type_id != dict_type_id {
        return None;
    }

    let x = cf_dict_get_i64(bounds_dict, "X")? as i32;
    let y = cf_dict_get_i64(bounds_dict, "Y")? as i32;
    let w = cf_dict_get_i64(bounds_dict, "Width")? as i32;
    let h = cf_dict_get_i64(bounds_dict, "Height")? as i32;
    Some((x, y, w, h))
}
