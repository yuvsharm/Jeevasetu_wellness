"use client";

import { useEffect,useRef,useState,type ReactNode } from "react";

export function Reveal({children,className=""}:{children:ReactNode;className?:string}){
  const ref=useRef<HTMLDivElement>(null);const [visible,setVisible]=useState(false);
  useEffect(()=>{const element=ref.current;if(!element)return;if(typeof IntersectionObserver==="undefined"){const timeout=window.setTimeout(()=>setVisible(true),0);return()=>window.clearTimeout(timeout)}const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting),{threshold:.12,rootMargin:"0px 0px -5%"});observer.observe(element);return()=>observer.disconnect()},[]);
  return <div ref={ref} className={`reveal-section ${visible?"is-visible":""} ${className}`}>{children}</div>;
}
