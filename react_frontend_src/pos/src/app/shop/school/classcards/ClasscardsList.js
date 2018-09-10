import React from "react"
import { v4 } from "uuid"

import AttendanceListItem from "./ClasscardsListItem"

const AttendanceList = ({attendance_items}) => 
    <div className="box box-default"> 
        <div className="box-body">
            {attendance_items.map((ai, i) => 
                <AttendanceListItem key={"ai_" + v4()}
                                    data={ai} />
            )}
        </div>
    </div>

export default AttendanceList